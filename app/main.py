import json
import os
import re
import traceback

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette import status
from starlette.requests import Request

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_from_json(domains_q: list):
    """
    [[domain,web,url]]
    :param domains_q:
    :return:
    """
    domains = []
    try:
        for domain in domains_q: # [[]]
            domains.append(domain)

    except Exception as e:
        ...

    return domains

def generate_dynamic_yml(domains, filename = "dynamic"):
    """
    Формирование dynamic.yml из массива доменов вида
    [[domain1.tld,web,traefik_dynamic_dummy:80], [domain2.tld,websecure,some-service:8000]]
    Где url - это локальный урл внутри докера до контеентера без http://

    :param domains:
    :param filename:
    :return:
    """

    yml_path = f"dynamic/{filename}.yml"
    routers = {}
    services = {
        'traefik-dynamic-dummy-80-service': {
            "loadBalancer": {
                "servers": [
                    {"url": "http://traefik_dynamic_dummy:80"}
                ]
            }
        }
    }

    for domain, entrypoints, service_url in domains:
        router_name = f"{re.sub(r'[^a-zA-Z0-9]', '-', domain)}-router"
        service_name = f"{re.sub(r'[^a-zA-Z0-9]', '-', service_url)}-service"
        entrypoints = entrypoints.split(",")
        router = {
            "rule": f"Host(`{domain}`)",
            "service": service_name,
            "entryPoints": entrypoints
        }
        if "websecure" in entrypoints:
            router["tls"] = {"certResolver": "letsencrypt"}

        routers[router_name] = router

        services[service_name] = {
            "loadBalancer": {
                "servers": [
                    {"url": f"{service_url}"}
                ]
            }
        }

    routes_len = len(routers.keys())
    if routers and services:
        yml_data = {
            "http": {
                "routers": routers,
                "services": services
            }
        }

        os.makedirs(os.path.dirname(yml_path), exist_ok=True)
        with open(yml_path, "w") as f:
            yaml.dump(
                yml_data,
                f,
                sort_keys=False,
            )

    return routes_len

@app.api_route("/", methods=["GET"])
async def hello():
    return {"hello_to": f"Traefik Dynamic"}

@app.api_route("/clean-acme", methods=["GET"])
async def clean_acme():
    """
    Очищает acme.json от неиспользуемых сертификатов, е домен был удален.
    Считывает домены из dynamic.yml и local.yml, затем удаляет
    из acme.json сертификаты для доменов, которые больше не используются.
    """
    host_regex = re.compile(r"Host\(`([^`]+)`\)") # Регулярное выражение для извлечения доменов из правил Host(`...`)
    config_paths = [
        'dynamic/dynamic.yml',
        'dynamic/local.yml'
    ]

    # 1 Собираю текущие активные домены из yml и уникализирую список доменов
    active_domains = set()
    for path in config_paths:
        if not os.path.exists(path): continue

        try:
            with open(path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                if not config_data or 'http' not in config_data or 'routers' not in config_data['http']: continue

                routers = config_data['http']['routers']
                for router_name, router_config in routers.items():
                    if 'rule' in router_config:
                        found_domains = host_regex.findall(router_config['rule'])
                        for domain in found_domains:
                            active_domains.add(domain)

        except Exception as e:
            print(f"Ошибка при чтении или парсинге файла {path}: {e}")

    if not active_domains: raise HTTPException(status_code=400, detail="Доменов не найдено")

    # 2 Проверка и очистка acme.json
    acme_path = 'data/acme.json'
    if not os.path.exists(acme_path): raise HTTPException(status_code=400, detail=f"Файл {acme_path} не найден. Очистка не требуется.")

    try:
        with open(acme_path, 'r', encoding='utf-8') as f:
            acme_data = json.load(f)

        # Предполагаем, что используется резолвер с именем 'letsencrypt'
        resolver_name = 'letsencrypt'
        if (
                resolver_name not in acme_data or
                not isinstance(acme_data[resolver_name].get('Certificates'), list)
        ):
            raise HTTPException(status_code=400, detail=f"В файле {acme_path} не найдена корректная структура для резолвера '{resolver_name}'.")

        # сколько доменов в acme.json всего
        len_original_certs = len(acme_data[resolver_name]['Certificates'])

        # Фильтруем сертификаты, оставляя только те, чей основной домен активен
        filtered_certs = [cert for cert in acme_data[resolver_name]['Certificates'] if cert.get('domain', {}).get('main') in active_domains]
        len_filtered_certs = len(filtered_certs)

        # если отфильтрованных столько же, то и удалять нечего
        if len_filtered_certs >= len_original_certs: raise HTTPException(status_code=400, detail="Неактивные сертификаты в acme.json не найдены. Очистка не требуется.")

        # иначе давайте почистим
        acme_data[resolver_name]['Certificates'] = filtered_certs
        with open(acme_path, 'w', encoding='utf-8') as f: json.dump(acme_data, f, indent=2)

        return dict(message=f"Очистка {acme_path} завершена. Удалено {len_original_certs - len_filtered_certs} неактивных сертификатов.")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка при обработке файла {acme_path}: {e}")

@app.api_route("/create", methods=["POST", "GET"])
async def create(request: Request):
    """
    Главная функция создания dynamic.yml для Traefik
    создает список их локального файла в data/.local.csv (если он есть)
    добавляет домены из POST запроса и складывает в dynsamic.yml

    :param request:
    :return:
    """
    params = await request.json() if request.method == "POST" else request.query_params

    # атентификация доступа по api_key
    apikey = os.getenv("APIKEY")
    if not params.get("apikey"): raise HTTPException(status_code=403, detail="API key is lost")
    if not apikey: raise HTTPException(status_code=403, detail="Set API Key for Traefik Dynamic")
    if apikey != params["apikey"]: raise HTTPException(status_code=403, detail="Invalid API Key")
    if 'domains' not in params: raise HTTPException(status_code=status.HTTP_418_IM_A_TEAPOT, detail="Nothing to add")

    try:
        # формируем массив доменов (на данном этапе не уникальных)
        # уникализация в generate_dynamic_yml
        filename = re.sub(r'[^a-zA-Z0-9]', '', params.get("filename", "dynamic").lower())
        routes_len = generate_dynamic_yml(json.loads(params['domains']), filename)
        return {"message": f"Ok {routes_len} domains were created.!"}

    except Exception as e:
        return {"message": str(e)}
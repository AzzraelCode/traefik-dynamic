import collections
import csv
import json
import os
import re

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_from_local():
    csv_path = "data/.local.csv"

    domains = []
    if os.path.exists(csv_path):
        with open(csv_path, newline="") as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if len(row) != 3: continue
                domains.append(row)

    return domains

def get_from_json(domains_str: str):
    """
    [[domain,web,url]]
    :param domains_str:
    :return:
    """
    domains = []
    try:
        for domain in json.loads(domains_str): # [[]]
            domains.append(domain)

    except Exception:
        ...

    return domains

def ordered_to_dict(obj):
    if isinstance(obj, collections.OrderedDict):
        return {k: ordered_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [ordered_to_dict(i) for i in obj]
    else:
        return obj

def generate_dynamic_yml(domains, yml_path="dynamic/dynamic.yml"):
    """
    Формирование dynamic.yml из массива доменов вида
    [[domain1.tld,web,traefik_dynamic_dummy:80], [domain2.tld,websecure,some-service:8000]]
    Где url - это локальный урл внутри докера до контеентера без http://

    :param domains:
    :param yml_path:
    :return:
    """

    routers = collections.OrderedDict()
    services = {
        'traefik-dynamic-dummy-80-service': {
            "loadBalancer": {
                "servers": [
                    {"url": "http://traefik_dynamic_dummy:80"}
                ]
            }
        }
    }

    for domain, entrypoint, service_url in domains:
        router_name = f"{re.sub(r'[^a-zA-Z0-9]', '-', domain)}-router"
        service_name = f"{re.sub(r'[^a-zA-Z0-9]', '-', service_url)}-service"

        router = {
            "rule": f"Host(`{domain}`)",
            "service": service_name,
            "entryPoints": [entrypoint]
        }
        if entrypoint == "websecure":
            router["tls"] = {"certResolver": "letsencrypt"}

        routers[router_name] = router

        services[service_name] = {
            "loadBalancer": {
                "servers": [
                    {"url": f"http://{service_url}"}
                ]
            }
        }

    routers['default_dummy'] = {
        "rule": "HostRegexp(`{any:.+}`)",
        "service": 'traefik-dynamic-dummy-80-service',
        'priority': 1,  # важно чтобы не перебить остальные роуты
        "entryPoints": ['web']  # но без tls чтобы не словать rate limit от LetsEncrypt
    }

    routers['fallback'] = {
        # "rule": "HostRegexp(`{any:.+}`)", # в конце всех роутов, без rule
        "service": 'traefik-dynamic-dummy-80-service',
        'priority': 0,  # важно чтобы не перебить остальные роуты
        "entryPoints": ['web']  # но без tls чтобы не словать rate limit от LetsEncrypt
    }

    yml_data = {
        "http": {
            "routers": routers,
            "services": services
        }
    }

    os.makedirs(os.path.dirname(yml_path), exist_ok=True)
    with open(yml_path, "w") as f:
        yaml.dump(
            ordered_to_dict(yml_data),
            f,
            sort_keys=False,
            default_flow_style=False
        )

@app.api_route("/", methods=["GET"])
async def hello():
    return {"hello_to": f"Traefik Dynamic"}

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

    try:
        # формируем массив доменов (на данном этапе не уникальных)
        # уникализация в generate_dynamic_yml
        domains = get_from_local()
        if 'domains' in params: domains += get_from_json(params["domains"])

        generate_dynamic_yml(domains)

        return {"message": f"Ok {len(domains)} domains were created.!"}
    except Exception as e:
        print(e)
        return {"message": str(e)}
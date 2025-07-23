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

def generate_dynamic_yml(domains, yml_path="dynamic/dynamic.yml"):
    """
    Формирование dynamic.yml из массива доменов вида
    [[domain1.tld,web,traefik_dynamic_dummy:80], [domain2.tld,websecure,some-service:8000]]
    Где url - это локальный урл внутри докера до контеентера без http://

    :param domains:
    :param yml_path:
    :return:
    """

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
        routes_len = generate_dynamic_yml(json.loads(params['domains']))
        return {"message": f"Ok {routes_len} domains were created.!"}

    except Exception as e:
        return {"message": str(e)}
# API для добавления доменов в Traefik

Это набор скриптов aka API для Traefik, для Docker. 
Чтобы динамически добалять/удалять в Traefik домены через POST/GET запрос.
Есть минимальная защита в виде API Key.

Под капотом Docker, Traefik, Docker Compose, Python + FastAPI. 

### Установка

0 Сначала
```bash
git clone https://github.com/AzzraelCode/traefik-dynamic.git /home/traefik-dynamic
cd /home/traefik-dynamic
```

1 Создай data/.env с содержимым, где API уникальный и сложный API Key
```bash
APIKEY="1234"
```

2 Создай data/acme.json c содержимым 
```json
{}
```

3 в traefik/dynamic/dynamic.yml можно создать след содержимое
```yaml
http:
  routers:
    catchall-router:
      rule: "HostRegexp(`{host:.+}`)"
      service: traefik-dynamic-dummy-80-service
      entryPoints:
        - web
  services:
    traefik-dynamic-dummy-80-service:
      loadBalancer:
        servers:
          - url: http://traefik_dynamic_dummy:80
```

4 Можно создать data/.local.csv c содержимым 
```csv
test1.tld,web,traefik_dynamic_dummy:80
test2.tld,web,traefik_dynamic_dummy:80
test3.tld,web,traefik_dynamic_dummy:80
```

5 Запускай
```bash
docker compose up -d
```

### Как передать домены в API

Если твой IP 1.2.3.4 и ты создал rule: "HostRegexp(`{host:.+}`)", то урл
http://1.2.3.4/traefik-dynamic-api/create?apikey=1234
перейди по нему и будет создан traefik/dynamic/dynamic.yml, кот подсосется в traefik
(!!! ВАЖНО !!! Текущий traefik/dynamic/dynamic.yml будет ПЕРЕЗАПИСАН)

traefik-dynamic-api/create?apikey=1234
можно передать POST/GET с полем domains
где его содержимое JSON Encoded
[[domain1.tld,web,service1], [domain1.tld,web,service1]]
оно суммируется с содержимым data/.local.csv, уникализируется и запишется в traefik/dynamic/dynamic.yml
после чего подсосется в traefik пости моментально (watch: true).
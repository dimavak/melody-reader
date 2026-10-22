# Свой сервер (VPS)

Тут ляжыць усё, што патрэбна, каб сервер распазнання працаваў на нашым VPS:

- [cloud-init.yaml](cloud-init.yaml) рыхтуе новы сервер: ставіць Docker, уключае брандмаўэр (адкрытыя толькі парты 22, 80 і 443), дадае 2 ГБ swap, уключае аўтаабнаўленні бяспекі і стварае карыстальніка `deploy`, праз якога заходзіць GitHub Actions.
- [caddy/](caddy/) апісвае адзіны ўваход на сервер. Caddy сам атрымлівае HTTPS-сертыфікаты і перадае кожны адрас свайму праекту. Новы праект дадае свой файл у `caddy/sites/`.
- [compose.yml](compose.yml) апісвае кантэйнер распазнавальніка.
- [../.github/workflows/deploy-server.yml](../.github/workflows/deploy-server.yml) пры кожнай змене кода капіюе файлы на сервер і перазапускае кантэйнеры.

На серверы ўсё ляжыць у `/srv/apps/<праект>`, а Caddy ў `/srv/apps/caddy`.

## Наладка (адзін раз)

### 1. SSH-ключ

На сваім камп'ютары (Windows PowerShell, macOS або Linux) выканайце:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/vps_deploy -C deploy
```

Пароль можна пакінуць пустым. З'явяцца два файлы: `vps_deploy.pub` (публічны ключ, яго можна паказваць) і `vps_deploy` (сакрэтны, яго нікому не паказвайце).

### 2. Сервер на Hetzner

1. Зарэгіструйцеся на https://console.hetzner.cloud і стварыце праект.
2. Націсніце **Add server** і выберыце:
   - Location: любая ў Еўропе (Falkenstein, Nuremberg, Helsinki);
   - Image: **Ubuntu 24.04**;
   - Type: Shared vCPU, x86, **CX22** (2 vCPU, 4 ГБ) або найменшы з 4 ГБ памяці;
   - Networking: пакіньце **Public IPv4** уключаным;
   - SSH keys: **Add SSH key** і ўстаўце змесціва `vps_deploy.pub`;
   - Cloud config: устаўце ўвесь файл [cloud-init.yaml](cloud-init.yaml).
3. Націсніце **Create & Buy now** і запішыце IP-адрас сервера. Праз 3–5 хвілін ён будзе гатовы.

### 3. GitHub

У рэпазіторыі адкрыйце Settings → Secrets and variables → Actions:

- на ўкладцы **Secrets** стварыце `SSH_KEY` і ўстаўце ўсё змесціва файла `vps_deploy` (разам з радкамі `-----BEGIN…` і `-----END…`);
- на ўкладцы **Variables** стварыце `SERVER_HOST` са значэннем IP сервера.

Калі ёсць свой дамен, дадайце яшчэ зменную `DOMAIN` (напрыклад, `example.org`) і накіруйце `*.example.org` на IP сервера. Без дамена адрас будзе `melody.<IP праз злучкі>.sslip.io`, і HTTPS на ім таксама працуе.

### 4. Запуск

У Actions запусціце **Deploy server**. Першая зборка займае каля 10 хвілін, бо спампоўваюцца homr і яго мадэлі. У канцы працэс правярае, што сервер адказвае, і паказвае яго адрас. Потым запусціце **Publish web app**, каб старонка даведалася гэты адрас.

## Карысныя каманды на серверы

```sh
ssh -i ~/.ssh/vps_deploy deploy@<IP>
docker ps                                            # што працуе
docker logs -f melody-recognizer                     # журнал распазнавальніка
cd /srv/apps/melody-reader/deploy && docker compose restart
```

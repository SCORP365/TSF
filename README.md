# TSF Connect — единый установщик

На VPS с Ubuntu 24.04 LTS amd64 выполните одну команду от root:

```bash
curl -fsSL https://raw.githubusercontent.com/SCORP365/TSF/3f058eb94e35b405a61d5b59fbdc7dcd31e3be97/install.sh -o /root/tsf-connect-install.sh && bash /root/tsf-connect-install.sh
```

Продолжение прерванной установки:

```bash
bash /root/tsf-connect-install.sh --resume
```

Bootstrap:
- устанавливает минимальные инструменты загрузки;
- выполняет GitHub Device Flow (QR-код и одноразовый код), без PAT;
- получает исходники приватного репозитория `SCORP365/TSF-Connect`;
- проверяет SHA-1 каждого Git blob относительно дерева Git;
- запускает основной серверный установщик из временного каталога и удаляет временные файлы.

Исходники остаются в приватном репозитории. Публичный репозиторий содержит только bootstrap.

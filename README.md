# Домашнее задание 11

## Запуск приложения

1. Установка зависимостей
```shell
uv init
source .venv/bin/activate
uv pip install -r requirements.txt
```

или 
```shell
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

2. Создание файла `.env`

```shell
cp env.example .env
```

P.S. Отредактируйте его по необходимости

3. Запуск приложения

```shell
uv run --active main.py
```

или 

```shell
python3 main.py
```

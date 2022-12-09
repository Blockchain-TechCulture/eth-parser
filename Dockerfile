FROM python:3.9-alpine3.16
WORKDIR /home/app
RUN apk update && apk add --no-cache bash
RUN apk --no-cache --update add build-base
COPY . .
RUN pip install -r requirements.txt
CMD ["python3", "main.py"]
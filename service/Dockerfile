FROM ubuntu:24.04
RUN apt-get update && apt-get upgrade -y

RUN apt-get install -y xinetd
RUN useradd author

COPY xinetd.conf /etc/xinetd.conf

WORKDIR /service
COPY ./bambi-notes ./bambi-notes
COPY ./entrypoint.sh ./entrypoint.sh

RUN mkdir /service/data
RUN chown author:author /service/data

RUN touch /var/log/xinetd.log
ENTRYPOINT bash entrypoint.sh


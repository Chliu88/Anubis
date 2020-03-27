#!/bin/bash


#
# Usage:
#   ./backup.sh # backs up elasticsearch and db data
#

set -ex

cd $(dirname $(realpath $0))
cd ..

TIMESTAMP="$(date +%s)"
BASE=".backups/${TIMESTAMP}"

mkdir -p ${BASE}


docker-compose exec db \
               mysqldump \
               -u root \
               --password=password \
               os | gzip - > ${BASE}/db.sql.gz


docker run \
       --rm \
       --volumes-from anubis_elasticsearch_1 \
       -v $(pwd):/backup \
       alpine \
       tar czf /backup/${BASE}/es.tar.gz \
       /usr/share/elasticsearch/data

if docker-compose ps | grep bomblab-request | grep Up &> /dev/null; then
    docker run \
           --rm \
           --volumes-from anubis_bomblab-request_1 \
           -w /opt/app \
           -v $(pwd):/backup \
           alpine \
           tar czf /backup/${BASE}/bomb.tar.gz \
           DATA
fi

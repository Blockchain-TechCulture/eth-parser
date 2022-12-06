# ETH and BNB PARSER

---

## Setup

1. clone project
2. Create .env files `cp .env.example .env`
3. Complete .env with credentials
4. `docker-compose build`
5. `docker-compose up -d`

## Network select

To use parser in eth or bnb networks simple change `NETWORK` credential settings:

| variable        | description                                       |
|-----------------|---------------------------------------------------|
| NETWORK         | Blockchain network. Can be `BEP20` or `ERC20`     |
| BASE_DIR        | Directory of parser. Change if use without docker |
| REDIS_HOST      | Address of your Redis server                      |
| REDIS_PORT      | Port of your Redis server                         |
| KAFKA_URL       | Address of your Kafka servers. Split by `,`       |
| KAFKA_TX_TOPIC  | Kafka topik to push transactions                  |
| RPC_URL         | Your blockchain URL                               |
| RPC_TESTNET_URL | Your test blockchain URL                          |
| TESTNET         | `True` or `False`                                 |



import json
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
from time import sleep, time

from eth_abi.exceptions import NonEmptyPaddingBytes
from kafka import KafkaProducer
from redis import Redis
from dotenv import dotenv_values
from web3 import Web3
from web3.exceptions import BlockNotFound
from web3.middleware import geth_poa_middleware
from web3.types import TxData


config = dotenv_values('.env')

NETWORK = config['NETWORK']

KAFKA_TOPIC = config['KAFKA_TX_TOPIC']

log_name = f'{NETWORK.lower()}_parser'
logging.basicConfig(
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(config['BASE_DIR'] + f'/logs/{log_name}.log', maxBytes=20000 * 15000, backupCount=10)
    ],
    level=logging.INFO,
    format='[%(asctime)s] [%(pathname)s:%(lineno)d] [%(levelname)s] - %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S'
)
logger = logging.getLogger(log_name)

abi_path = Path(config['BASE_DIR'] , 'abi', f'{NETWORK.lower()}_abi.json')
with open(abi_path) as abi_file:
    abi = json.loads(abi_file.read())

tokens_path = Path(config['BASE_DIR'] , 'token_list.json')
with open(tokens_path) as token_file:
    tokens = json.loads(token_file.read())

r = Redis(host=config['REDIS_HOST'], port=int(config['REDIS_PORT']))
servers = config['KAFKA_URL'].split(',')
producer = KafkaProducer(bootstrap_servers=servers, value_serializer=lambda v: json.dumps(v).encode('utf-8'))

network_testnet = config['TESTNET'].lower() in ('true', '1', 't')
RPC_URL= config['RPC_TESTNET_URL'] if network_testnet else config['RPC_URL']


class Worker:
    def __init__(self):
        self.web3 = Web3(Web3.HTTPProvider(RPC_URL))
        if NETWORK == 'BEP20':
            self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
        last_block = r.get(f'{NETWORK}_last_block')
        self.last_block_num = int(last_block) + 1 if last_block else self.web3.eth.get_block_number()
        if self.last_block_num is None:
            raise Exception('cannot read last block')
        self.contracts = []

    def consume(self):
        self.load_contracts()
        block_number = self.last_block_num
        while True:
            try:
                get_block = self.web3.eth.get_block(block_number, True)
            except BlockNotFound as e:
                logger.info(e)
                get_block = None
            if get_block is None:
                sleep(7) # average new block creation time
            else:
                # saved transaction first
                try:
                    new_tx = [member.decode("utf-8") for member in r.smembers('ethereum_new_tx')]
                    if len(new_tx) > 0:
                        logger.info(f'check unconfirmed transactions {block_number}')
                        txs = []
                        for tx_hash in new_tx:
                            receipt = self.web3.eth.get_transaction(tx_hash)
                            txs.append(receipt)
                        self.parse(txs)
                except Exception as e:
                    logger.error(e)
                # new transaction second
                try:
                    logger.info(f'new block {block_number}')
                    txs = get_block.get('transactions')
                    self.parse(txs)
                    r.set(f'{NETWORK}_last_block', block_number)
                    block_number = block_number + 1
                except Exception as e:
                    logger.error(e)


    def load_contracts(self):
        for token in tokens:
            if token['address'] == "" or token['type'] != NETWORK or token['name'] in ['ETH', 'BNB']:
                continue
            print(token['address'], token['name'])
            address = self.web3.toChecksumAddress(token['address'])
            contract = self.web3.eth.contract(address=address, abi=abi)
            contract_data = {
                'data': contract,
                'address': token['address'],
                'currency': token['name'],
                'decimal': token['decimal'],
            }
            self.contracts.append(contract_data)

    def parse(self, txs):
        start_time = time()
        for tx in txs:
            tx_data = None
            if tx.input[:8] == '0xa9059c':
                tx_data = self.__token_transfer_parser(tx)
            elif tx.input == '0x':
                tx_data = self.__transfer_parser(tx)
            if tx_data is not None:
                r.srem(f'{NETWORK}_new_tx', tx_data['hex'])
                producer.send(KAFKA_TOPIC, tx_data)
        logger.info(f'{len(txs)}  parsed. time {time() - start_time}')

    def __transfer_parser(self, tx_info: TxData):
        amount = int(tx_info['value']) / 10 ** 18
        currency = 'ETH' if NETWORK == 'ERC20' else 'BNB'
        return {
            'from_address': tx_info['from'],
            "txid": tx_info['hash'].hex(),
            'value': str(amount),
            'hex': tx_info['hash'].hex(),
            'to_address': tx_info['to'],
            "confirmations": 13,
            'block_number': int(tx_info['blockNumber']),
            'block_hash': None,
            'decimal': 18,
            'currency': currency,
            'network': NETWORK,
        }

    def __token_transfer_parser(self, tx_info: TxData):
        contract = self.get_contract_data(getattr(tx_info, 'to'))
        if contract is None:
            return None
        try:
            data = contract['data'].decode_function_input(getattr(tx_info, 'input'))
        except NonEmptyPaddingBytes as e:
            logger.info(e, getattr(tx_info, 'hash').hex())
            return None
        to_address = data[-1]['dst']
        amount = int(data[-1]['wad']) / 10 ** int(contract['decimal'])
        tx_data = {
            "from_address": getattr(tx_info, 'from'),
            "txid": getattr(tx_info, 'hash').hex(),
            "value": str(amount),
            "hex": getattr(tx_info, 'hash').hex(),
            "to_address": to_address,
            "confirmations": 13,
            "block_number": getattr(tx_info, 'blockNumber'),
            "block_hash": None,
            "decimal": contract['decimal'],
            "network": NETWORK,
            "currency": contract['currency'],
            # "status": 'confirmed'
        }
        return tx_data

    def get_contract_data(self, address: str):
        if address is None:
            return None
        for contract in self.contracts:
            if contract['address'].lower() == address.lower():
                return contract
        return None

def main():
    Worker().consume()

if __name__ == '__main__':
    main()

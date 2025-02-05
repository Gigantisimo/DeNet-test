from web3 import Web3
from typing import List, Tuple, Dict, Union
from datetime import datetime
from flask import Flask, request, jsonify
import requests
import time

# Инициализация подключения к Polygon
POLYGON_RPC_URL = "https://polygon-rpc.com"
CONTRACT_ADDRESS = "0x1a9b54a3075119f1546c52ca0940551a6ce5d2d0"
API_KEY = "////"

# Стандартный ABI для токена ERC20
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

class TokenTracker:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(POLYGON_RPC_URL))
        self.contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(CONTRACT_ADDRESS),
            abi=ERC20_ABI
        )
        self.decimals = self.contract.functions.decimals().call()
        self._balance_cache = {}
        self._tx_cache = {}
        self._token_info_cache = None
        self._cache_lifetime = 300
        self._last_cache_update = 0

    def _is_cache_valid(self) -> bool:
        return time.time() - self._last_cache_update < self._cache_lifetime

    def _update_cache_timestamp(self):
        self._last_cache_update = time.time()

    def format_balance(self, balance: int) -> float:
        return balance / (10 ** self.decimals)

    def get_balance(self, address: str) -> float:
        address = self.w3.to_checksum_address(address)
        if self._is_cache_valid() and address in self._balance_cache:
            return self._balance_cache[address]
            
        try:
            balance = self.contract.functions.balanceOf(address).call()
            formatted_balance = self.format_balance(balance)
            self._balance_cache[address] = formatted_balance
            self._update_cache_timestamp()
            return formatted_balance
        except Exception as e:
            print(f"Error getting balance for {address}: {e}")
            return 0

    def get_balance_batch(self, addresses: List[str]) -> List[float]:
        return [self.get_balance(addr) for addr in addresses]

    def _get_token_transactions(self) -> List[dict]:
        if self._is_cache_valid() and self._tx_cache:
            return self._tx_cache
            
        ETHERSCAN_API = "https://api.etherscan.io/v2/api"
        params = {
            'chainid': '137',
            'module': 'account',
            'action': 'tokentx',
            'contractaddress': CONTRACT_ADDRESS,
            'page': '1',
            'offset': '1000',
            'sort': 'desc',
            'apikey': API_KEY
        }
        
        try:
            response = requests.get(ETHERSCAN_API, params=params)
            data = response.json()
            
            if data['status'] == '1' and 'result' in data:
                self._tx_cache = data['result']
                self._update_cache_timestamp()
                return self._tx_cache
            return []
        except Exception as e:
            print(f"Error getting transactions: {e}")
            return []

    def get_top_holders(self, n: int) -> List[Tuple[str, float]]:
        transactions = self._get_token_transactions()
        if not transactions:
            return []
            
        addresses = set()
        for tx in transactions:
            addresses.add(tx['from'])
            addresses.add(tx['to'])
        
        holders = []
        for address in addresses:
            if address != "0x0000000000000000000000000000000000000000":
                try:
                    balance = self.get_balance(address)
                    if balance > 0:
                        holders.append((address, balance))
                except Exception as e:
                    print(f"Error getting balance for {address}: {e}")
                    continue
        
        return sorted(holders, key=lambda x: x[1], reverse=True)[:n]

    def get_top_with_transactions(self, n: int) -> List[Tuple[str, float, str]]:
        transactions = self._get_token_transactions()
        if not transactions:
            return []
            
        holders_data = {}
        
        for tx in transactions:
            for address in [tx['to'], tx['from']]:
                if address not in holders_data and address != "0x0000000000000000000000000000000000000000":
                    try:
                        balance = self.get_balance(address)
                        if balance > 0:
                            timestamp = datetime.fromtimestamp(int(tx['timeStamp']))
                            holders_data[address] = {
                                'balance': balance,
                                'last_tx': timestamp.strftime('%Y-%m-%d %H:%M:%S')
                            }
                    except Exception as e:
                        print(f"Error getting balance for {address}: {e}")
                        continue
        
        sorted_holders = sorted(
            [(addr, data['balance'], data['last_tx']) 
             for addr, data in holders_data.items()],
            key=lambda x: x[1],
            reverse=True
        )[:n]
        
        return sorted_holders

    def get_token_info(self) -> Dict[str, Union[str, int]]:
        try:
            if self._is_cache_valid() and self._token_info_cache:
                return self._token_info_cache

            symbol = self.contract.functions.symbol().call()
            name = self.contract.functions.name().call()
            total_supply = self.contract.functions.totalSupply().call()
            
            info = {
                "symbol": symbol,
                "name": name,
                "totalSupply": self.format_balance(total_supply)
            }

            self._token_info_cache = info
            self._update_cache_timestamp()
            return info
        except Exception as e:
            print(f"Error getting token info: {e}")
            return {}

    def get_token_stats(self) -> Dict[str, Union[str, int, float]]:
        """Получение расширенной статистики по токену"""
        try:
            basic_info = self.get_token_info()
            holders = self.get_top_holders(100)
            
            total_held = sum(balance for _, balance in holders)
            unique_holders = len(holders)
            
            return {
                **basic_info,
                "unique_holders": unique_holders,
                "total_held": total_held,
                "average_balance": total_held / unique_holders if unique_holders > 0 else 0
            }
        except Exception as e:
            print(f"Error getting token stats: {e}")
            return {}

    def get_address_history(self, address: str, limit: int = 100) -> List[Dict]:
        """Получение истории транзакций для адреса"""
        try:
            transactions = self._get_token_transactions()
            address = self.w3.to_checksum_address(address)
            
            address_txs = []
            for tx in transactions:
                if tx['to'].lower() == address.lower() or tx['from'].lower() == address.lower():
                    timestamp = datetime.fromtimestamp(int(tx['timeStamp']))
                    address_txs.append({
                        'type': 'receive' if tx['to'].lower() == address.lower() else 'send',
                        'counterparty': tx['from'] if tx['to'].lower() == address.lower() else tx['to'],
                        'amount': self.format_balance(int(tx['value'])),
                        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    })
                    
                if len(address_txs) >= limit:
                    break
                    
            return address_txs
        except Exception as e:
            print(f"Error getting address history: {e}")
            return []

# Инициализация Flask приложения
app = Flask(__name__)
tracker = TokenTracker()

@app.route('/api/docs')
def api_documentation():
    """API Documentation endpoint"""
    return jsonify({
        "version": "1.0.0",
        "description": "Polygon Token Tracker API",
        "endpoints": {
            "GET /get_balance": {
                "description": "Get balance for a specific address",
                "params": {"address": "string (required) - Ethereum address"},
                "example": "/get_balance?address=0x51f1774249Fc2B0C2603542Ac6184Ae1d048351d"
            },
            "POST /get_balance_batch": {
                "description": "Get balances for multiple addresses",
                "body": {"addresses": "array of strings (required) - List of Ethereum addresses"},
                "example": {"addresses": ["0x51f1774249Fc2B0C2603542Ac6184Ae1d048351d"]}
            },
            "GET /get_top": {
                "description": "Get top N holders by balance",
                "params": {"n": "integer (optional, default: 10) - Number of holders to return"},
                "example": "/get_top?n=5"
            },
            "GET /get_top_with_transactions": {
                "description": "Get top N holders with their last transaction dates",
                "params": {"n": "integer (optional, default: 10) - Number of holders to return"},
                "example": "/get_top_with_transactions?n=5"
            },
            "GET /token_info": {
                "description": "Get basic token information",
                "example": "/token_info"
            },
            "GET /token_stats": {
                "description": "Get extended token statistics",
                "example": "/token_stats"
            },
            "GET /address_history": {
                "description": "Get transaction history for an address",
                "params": {
                    "address": "string (required) - Ethereum address",
                    "limit": "integer (optional, default: 100) - Maximum number of transactions"
                },
                "example": "/address_history?address=0x51f1774249Fc2B0C2603542Ac6184Ae1d048351d&limit=10"
            }
        }
    })

@app.route('/get_balance', methods=['GET'])
def api_get_balance():
    address = request.args.get('address')
    if not address:
        return jsonify({"error": "Address parameter is required"}), 400
    
    try:
        balance = tracker.get_balance(address)
        return jsonify({"balance": balance})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/get_balance_batch', methods=['POST'])
def api_get_balance_batch():
    data = request.get_json()
    if not data or 'addresses' not in data:
        return jsonify({"error": "Addresses are required in request body"}), 400
    
    try:
        balances = tracker.get_balance_batch(data['addresses'])
        return jsonify({"balances": balances})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/get_top', methods=['GET'])
def api_get_top():
    try:
        n = request.args.get('n', default=10, type=int)
        if n <= 0:
            return jsonify({"error": "Parameter 'n' must be positive"}), 400
        
        top_holders = tracker.get_top_holders(n)
        return jsonify({
            "top_holders": [
                {"address": address, "balance": balance}
                for address, balance in top_holders
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/get_top_with_transactions', methods=['GET'])
def api_get_top_with_transactions():
    try:
        n = request.args.get('n', default=10, type=int)
        if n <= 0:
            return jsonify({"error": "Parameter 'n' must be positive"}), 400
        
        top_holders = tracker.get_top_with_transactions(n)
        return jsonify({
            "holders": [
                {
                    "address": address,
                    "balance": balance,
                    "last_transaction": last_tx
                }
                for address, balance, last_tx in top_holders
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/token_info', methods=['GET'])
def api_token_info():
    try:
        info = tracker.get_token_info()
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/token_stats')
def api_token_stats():
    """Get extended token statistics"""
    try:
        stats = tracker.get_token_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/address_history')
def api_address_history():
    """Get transaction history for an address"""
    address = request.args.get('address')
    limit = request.args.get('limit', default=100, type=int)
    
    if not address:
        return jsonify({"error": "Address parameter is required"}), 400
        
    try:
        history = tracker.get_address_history(address, limit)
        return jsonify({
            "address": address,
            "transactions": history
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)

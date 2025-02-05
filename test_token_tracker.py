import unittest
from unittest.mock import Mock, patch
from datetime import datetime
from bot import TokenTracker, app

class TestTokenTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = TokenTracker()
        self.test_address = "0x51f1774249Fc2B0C2603542Ac6184Ae1d048351d"
        
    @patch('web3.eth.Contract')
    def test_get_balance(self, mock_contract):
        # Mock contract response
        mock_contract.functions.balanceOf.return_value.call.return_value = 10000000000000000
        
        balance = self.tracker.get_balance(self.test_address)
        self.assertEqual(balance, 0.01)
        
    def test_get_balance_batch(self):
        test_addresses = [
            self.test_address,
            "0x4830AF4aB9cd9E381602aE50f71AE481a7727f7C"
        ]
        balances = self.tracker.get_balance_batch(test_addresses)
        self.assertEqual(len(balances), 2)
        
    def test_get_top_holders(self):
        result = self.tracker.get_top_holders(2)
        self.assertLessEqual(len(result), 2)
        
    def test_get_token_info(self):
        info = self.tracker.get_token_info()
        self.assertIn('symbol', info)
        self.assertIn('name', info)
        self.assertIn('totalSupply', info)

class TestAPI(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        
    def test_get_balance_endpoint(self):
        response = self.client.get(f'/get_balance?address={self.test_address}')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('balance', data)
        
    def test_get_balance_batch_endpoint(self):
        addresses = [
            "0x51f1774249Fc2B0C2603542Ac6184Ae1d048351d",
            "0x4830AF4aB9cd9E381602aE50f71AE481a7727f7C"
        ]
        response = self.client.post('/get_balance_batch', 
                                  json={"addresses": addresses})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('balances', data)
        
    def test_get_top_endpoint(self):
        response = self.client.get('/get_top?n=2')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('top_holders', data)

if __name__ == '__main__':
    unittest.main()
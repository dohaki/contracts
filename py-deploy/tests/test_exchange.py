import time

import pytest

from tldeploy.core import deploy_network, deploy_exchange, deploy
from tldeploy.exchange import Order
from tldeploy.signing import priv_to_pubkey
from eth_utils import to_checksum_address


trustlines = [(0, 1, 100, 150),
              (1, 2, 200, 250),
              (2, 3, 300, 350),
              (3, 4, 400, 450),
              (0, 4, 500, 550)
              ]  # (A, B, clAB, clBA)


NULL_ADDRESS = '0x0000000000000000000000000000000000000000'


@pytest.fixture()
def accounts(web3, tester):
    """list of accounts, with account[0] being the maker,i.e. tester.a0 address"""
    accounts = [tester.a0] + web3.personal.listAccounts[0:4]
    assert len(accounts) == 5
    return [to_checksum_address(account) for account in accounts]


@pytest.fixture()
def exchange_contract(web3):
    return deploy_exchange(web3)


@pytest.fixture()
def currency_network_contract(web3):
    return deploy_network(web3, name="TestCoin", symbol="T", decimals=6, fee_divisor=0)


@pytest.fixture()
def token_contract(web3, accounts):
    A, B, C, *rest = accounts
    contract = deploy("DummyToken", web3, 'DummyToken', 'DT', 18, 10000000)
    contract.transact().setBalance(A, 10000)
    contract.transact().setBalance(B, 10000)
    contract.transact().setBalance(C, 10000)
    return contract


@pytest.fixture()
def currency_network_contract_with_trustlines(currency_network_contract, exchange_contract, accounts):
    contract = currency_network_contract
    for (A, B, clAB, clBA) in trustlines:
        contract.transact().setAccount(accounts[A], accounts[B], clAB, clBA, 0, 0, 0, 0, 0, 0)
    contract.transact().addAuthorizedAddress(exchange_contract.address)
    return contract


def test_order_hash(exchange_contract, token_contract, currency_network_contract_with_trustlines, accounts):
    maker_address, taker_address, *rest = accounts

    order = Order(exchange_contract.address,
                  maker_address,
                  NULL_ADDRESS,
                  token_contract.address,
                  currency_network_contract_with_trustlines.address,
                  NULL_ADDRESS,
                  100,
                  50,
                  0,
                  0,
                  1234,
                  1234
                  )

    assert order.hash() == exchange_contract.call().getOrderHash(
        [order.maker_address,
         order.taker_address,
         order.maker_token,
         order.taker_token,
         order.fee_recipient],
        [order.maker_token_amount,
         order.taker_token_amount,
         order.maker_fee,
         order.taker_fee,
         order.expiration_timestamp_in_sec,
         order.salt]
    )


def test_order_signature(
        exchange_contract,
        token_contract,
        currency_network_contract_with_trustlines,
        accounts,
        tester):
    maker_address, taker_address, *rest = accounts

    order = Order(exchange_contract.address,
                  maker_address,
                  NULL_ADDRESS,
                  token_contract.address,
                  currency_network_contract_with_trustlines.address,
                  NULL_ADDRESS,
                  100,
                  50,
                  0,
                  0,
                  1234,
                  1234
                  )

    v, r, s = order.sign(tester.k0)

    assert exchange_contract.call().isValidSignature(maker_address, order.hash().hex(), v, r, s)


def test_exchange(exchange_contract, token_contract, currency_network_contract_with_trustlines, accounts, tester):
    maker_address, mediator_address, taker_address, *rest = accounts

    assert token_contract.call().balanceOf(maker_address) == 10000
    assert token_contract.call().balanceOf(taker_address) == 10000
    assert currency_network_contract_with_trustlines.call().balance(maker_address, mediator_address) == 0
    assert currency_network_contract_with_trustlines.call().balance(mediator_address, taker_address) == 0

    token_contract.transact({'from': maker_address}).approve(exchange_contract.address, 100)

    order = Order(exchange_contract.address,
                  maker_address,
                  NULL_ADDRESS,
                  token_contract.address,
                  currency_network_contract_with_trustlines.address,
                  NULL_ADDRESS,
                  100,
                  50,
                  0,
                  0,
                  int(time.time()+60*60*24),
                  1234
                  )

    assert priv_to_pubkey(tester.k0) == maker_address

    v, r, s = order.sign(tester.k0)

    exchange_contract.transact({'from': taker_address}).fillOrderTrustlines(
          [order.maker_address, order.taker_address, order.maker_token, order.taker_token, order.fee_recipient],
          [order.maker_token_amount, order.taker_token_amount, order.maker_fee,
           order.taker_fee, order.expiration_timestamp_in_sec, order.salt],
          50,
          [],
          [mediator_address, maker_address],
          v,
          r,
          s)

    assert token_contract.call().balanceOf(maker_address) == 9900
    assert token_contract.call().balanceOf(taker_address) == 10100
    assert currency_network_contract_with_trustlines.call().balance(maker_address, mediator_address) == 50
    assert currency_network_contract_with_trustlines.call().balance(taker_address, mediator_address) == -50

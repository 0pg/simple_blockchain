import hashlib, math
import json, requests
from time import time
from textwrap import dedent
from uuid import uuid4

from urllib.parse import urlparse
from collections import OrderedDict
from flask import Flask, jsonify, request

class Blockchain(object):
	def __init__(self):
		self.past_transaction = OrderedDict()
		self.merkle = []
		self.chain = []
		self.current_transactions = []
		self.nodes = set()
		self.new_block(previous_hash=1)

	def new_block(self, previous_hash=None):
		block_header = {
			'index' : len(self.chain) + 1,
			'timestamp' : time(),
			'proof' : 0, 
			'previous_hash' : previous_hash or self.hash(self.chain[-1]),
			'transaction_hash': self.merkle,
		}
		block_header = self.proof_of_work(block_header)
		block_hash = self.hash(block_header)
		transactions = self.current_transactions 
		print(self.current_transactions)
		block = {
			'block_hash' : block_hash,
			'block_header' : block_header, 
			'transactions' : transactions,
			}
		self.current_transactions = []

		self.chain.append(block)
		return block
	def register_node(self, address):
		parsed_url = urlparse(address)
		if parsed_url.netloc:
			self.nodes.add(parsed_url.netloc)
		elif parsed_url.path:
            # Accepts an URL without scheme like '192.168.0.5:5000'.
			self.nodes.add(parsed_url.path)
		else:
			raise ValueError('Invalid URL')		

	def new_transaction(self, sender, recipient, amount):
		self.current_transactions.append({
			'sender' : sender,
			'recipient' : recipient,
			'amount' : amount,
			})

		return self.last_block['block_header']['index'] + 1

	def transaction_record(self,merkle):
		past_transaction = self.past_transaction
		length = len(merkle)
		dep = int(math.log2(length))
		nodes = pow(2,dep)
		extra_nodes = length - nodes
		non = 2 * extra_nodes + pow(2,dep+1) - 1
		
		for index in range(0, extra_nodes):
			left = merkle.pop(index)
			right = merkle.pop(index)
			left_hash = self.hash(left)
			right_hash = self.hash(right)
			past_transaction[non] = left_hash
			non -= 1
			past_transaction[non] = right_hash
			non -= 1
			merkle.insert(index, left_hash+right_hash)

		while True:  
			length = len(merkle)
			dep = int(math.log2(length))
			nodes = pow(2,dep)      
			
			for index in range(0, int(nodes/2)):
				left = merkle.pop(index)
				left_hash = self.hash(left)
				past_transaction[non] = left_hash
				non -= 1
				right = merkle.pop(index)
				right_hash = self.hash(right)
				past_transaction[non] = right_hash
				non -= 1
				merkle.insert(index, left_hash+right_hash)
		
			if length is 1:
				merkle = self.hash(merkle)
				past_transaction[non] = merkle
				self.past_transaction = past_transaction
				self.merkle = merkle
				break

	def proof_of_work(self, block_h):
		while self.valid_proof(block_h) is False:
			block_h['proof'] += 1

		return block_h

	def valid_chain(self, chain):
		last_block = chain[0]
		current_index = 1

		while current_index < len(chain):
			block = chain[current_index]
			block_h = block['block_header']
			print("{}".format(last_block))
			print("{}".format(block))
			print("\n------------\n")

			if block_h['previous_hash'] != last_block['block_hash']:
				return False

			if not self.valid_proof(block_h):
				return False

			last_block = block
			current_index += 1
		return True


	def resolve_conflicts(self):
		neighbours = self.nodes
		new_chain = None
		max_length = len(self.chain)
		for node in neighbours:
			response = requests.get('http://{}/chain'.format(node))

			if response.status_code == 200 :
				length = response.json()['length']
				chain = response.json()['chain']

				if length > max_length and self.valid_chain(chain):
					max_length = length
					new_chain = chain

		if new_chain:
			self.chain = new_chain
			return True

		return False



	@staticmethod
	def hash(key):
		key_string = json.dumps(key, sort_keys=True).encode()
		return hashlib.sha256(key_string).hexdigest()

	def valid_proof(self, block_h):
		guess_hash = self.hash(block_h)
		if guess_hash[ :4] == "0000":
			print(block_h)
			return guess_hash
		else:
			return False

	@property
	def last_block(self):
		return self.chain[-1]

app = Flask(__name__)

node_identifier = str(uuid4()).replace('-', '')

blockchain = Blockchain()

@app.route('/mine', methods=['GET'])
def mine():
	last_block = blockchain.last_block

	blockchain.new_transaction(
		sender="0",
		recipient=node_identifier,
		amount=1,
		)

	previous_hash = last_block['block_hash']
	merkle = blockchain.current_transactions
	blockchain.transaction_record(merkle)
	block = blockchain.new_block(previous_hash)

	# response = {
	# 	'message' : "New block Forged",
	# 	'index' : block['index'],
	# 	'transactions' : block['transactions'],
	# 	'proof' : block['proof'],
	# 	'previous_hash' : block['previous_hash'],
	# 	'transaction_hash' : block['transaction_hash'],
	# }
	response = block
	return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
	values = request.get_json(force=True)
	print(values)
	required = ['sender', 'recipient', 'amount']
	if not all(k in values for k in required):
		return 'Missing values', 400

	index = blockchain.new_transaction(values['sender'], values['recipient'], values['amount'])
		
	response = {'message': 'Transaction will be added to Block {}'.format(index)}
	return jsonify(response), 201
	

@app.route('/chain', methods=['GET'])
def full_chain():
	response = {
		'chain' : blockchain.chain,
		'length' : len(blockchain.chain), 
	}
	return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
	values = request.get_json(force=True)

	nodes = values.get('nodes')
	if nodes is None:
		return "Error: Plesae supply a valid lsit of nodes", 400

	for node in nodes:
		blockchain.register_node(node)

	response = {
		'message': 'New nodes have been added',
		'total_nodes': list(blockchain.nodes)
	}

	return jsonify(response), 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
	replaced = blockchain.resolve_conflicts()

	if replaced:
		response = {
			'message': 'Our chain was replaced',
			'new_chain': blockchain.chain
		}
	else:
		response = {
			'message': 'Our chain is authoritative',
			'chain': blockchain.chain
		}
	return jsonify(response), 200

if __name__ == '__main__':
	#app.run(host='0.0.0.0', port=5000)
	from argparse import ArgumentParser

	parser = ArgumentParser()
	parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
	args = parser.parse_args()
	port = args.port

	app.run(host='0.0.0.0', port=port)

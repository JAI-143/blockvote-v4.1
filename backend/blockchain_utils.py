"""
blockchain_utils.py
Wraps Web3.py for interacting with the deployed VotingSystem contract.
Falls back to simulation mode if Ganache is not running.
"""

import hashlib, json, os, time
from datetime import datetime


class BlockchainUtils:

    GANACHE_URL = "http://127.0.0.1:7545"

    # Default candidates shown when blockchain is offline
    _DEFAULT_CANDIDATES = [
        {"id": 1, "name": "Alice Johnson",  "party": "Progressive Party", "votes": 0},
        {"id": 2, "name": "Bob Smith",      "party": "Liberty Party",     "votes": 0},
        {"id": 3, "name": "Carol Williams", "party": "Unity Party",       "votes": 0},
    ]

    def __init__(self, base_dir: str):
        self.base_dir  = base_dir
        self.w3        = None
        self.contract  = None
        self.account   = None
        self._sim_votes = {1: 0, 2: 0, 3: 0}   # fallback in-memory counts
        self._sim_file  = os.path.join(base_dir, "database", "sim_votes.json")
        self._load_sim_votes()
        self._connect()

    # ─── Initialisation ───────────────────────────────────────────────────────

    def _connect(self):
        try:
            from web3 import Web3
            self.w3 = Web3(Web3.HTTPProvider(self.GANACHE_URL))
            if self.w3.is_connected():
                self.account = self.w3.eth.accounts[0]
                self._load_contract()
                print(f"✅  Blockchain connected — account: {self.account[:10]}...")
                return
        except Exception as e:
            print(f"⚠️  Web3 error: {e}")
        print("⚠️  Ganache offline — running in SIMULATION mode")

    def _load_contract(self):
        abi_path  = os.path.join(self.base_dir, "blockchain", "contract_abi.json")
        addr_path = os.path.join(self.base_dir, "blockchain", "contract_address.txt")
        if not (os.path.exists(abi_path) and os.path.exists(addr_path)):
            print("⚠️  Contract not deployed yet. Run: python blockchain/deploy.py")
            return
        try:
            from web3 import Web3
            with open(abi_path)  as f: abi     = json.load(f)
            with open(addr_path) as f: address = f.read().strip()
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(address), abi=abi
            )
            print(f"✅  Smart contract loaded — {address[:12]}...")
        except Exception as e:
            print(f"⚠️  Contract load error: {e}")

    # ─── Simulation Persistence ───────────────────────────────────────────────

    def _load_sim_votes(self):
        if os.path.exists(self._sim_file):
            try:
                with open(self._sim_file) as f:
                    data = json.load(f)
                self._sim_votes = {int(k): v for k, v in data.items()}
            except Exception:
                pass

    def _save_sim_votes(self):
        os.makedirs(os.path.dirname(self._sim_file), exist_ok=True)
        with open(self._sim_file, "w") as f:
            json.dump(self._sim_votes, f)

    # ─── Public API ───────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self.w3 is not None and self.w3.is_connected() and self.contract is not None

    def get_candidates(self) -> list[dict]:
        if self.is_connected():
            try:
                count = self.contract.functions.candidateCount().call()
                result = []
                for i in range(1, count + 1):
                    cid, name, party, votes = self.contract.functions.getCandidate(i).call()
                    result.append({"id": cid, "name": name, "party": party, "votes": votes})
                return result
            except Exception as e:
                print(f"get_candidates error: {e}")

        # Simulation fallback
        return [
            {**c, "votes": self._sim_votes.get(c["id"], 0)}
            for c in self._DEFAULT_CANDIDATES
        ]

    def cast_vote(self, voter_hash_hex: str, candidate_id: int) -> str:
        if self.is_connected():
            try:
                voter_bytes = bytes.fromhex(voter_hash_hex[:64].ljust(64, "0"))
                tx  = self.contract.functions.castVote(
                    voter_bytes, candidate_id
                ).transact({"from": self.account, "gas": 200_000})
                rec = self.w3.eth.wait_for_transaction_receipt(tx)
                return rec["transactionHash"].hex()
            except Exception as e:
                print(f"cast_vote blockchain error: {e}")

        # Simulation fallback
        self._sim_votes[candidate_id] = self._sim_votes.get(candidate_id, 0) + 1
        self._save_sim_votes()
        fake_hash = hashlib.sha256(f"{voter_hash_hex}{time.time()}".encode()).hexdigest()
        return f"SIM_{fake_hash}"

    def get_mode(self) -> str:
        return "BLOCKCHAIN" if self.is_connected() else "SIMULATION"

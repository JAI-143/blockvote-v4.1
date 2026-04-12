"""
deploy.py
Compiles VotingContract.sol and deploys it to the local Ganache blockchain.
Run this ONCE after starting Ganache.
"""

import os, sys, json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def deploy():
    print("\n" + "="*55)
    print("   BLOCKCHAIN VOTING SYSTEM — CONTRACT DEPLOYMENT")
    print("="*55)

    # ── 1. Connect to Ganache ───────────────────────────────────
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:7545"))

    if not w3.is_connected():
        print("\n❌  Cannot connect to Ganache!")
        print("    Start Ganache first:  ganache --port 7545 --deterministic\n")
        sys.exit(1)

    print(f"✅  Connected to Ganache  |  Chain ID: {w3.eth.chain_id}")
    print(f"    Deployer account: {w3.eth.accounts[0]}")
    print(f"    Balance: {w3.from_wei(w3.eth.get_balance(w3.eth.accounts[0]), 'ether')} ETH")

    # ── 2. Install + Compile Solidity ───────────────────────────
    print("\n📦  Installing Solidity compiler (one-time, may take a minute)...")
    from solcx import compile_standard, install_solc
    install_solc("0.8.19")
    print("✅  Solidity 0.8.19 ready")

    sol_path = os.path.join(BASE_DIR, "blockchain", "VotingContract.sol")
    with open(sol_path, "r") as f:
        source = f.read()

    print("🔨  Compiling smart contract...")
    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {"VotingContract.sol": {"content": source}},
            "settings": {
                "outputSelection": {
                    "*": {"*": ["abi", "evm.bytecode"]}
                }
            },
        },
        solc_version="0.8.19",
    )

    contract_data = compiled["contracts"]["VotingContract.sol"]["VotingSystem"]
    abi      = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]
    print("✅  Contract compiled successfully")

    # ── 3. Save ABI ─────────────────────────────────────────────
    abi_path = os.path.join(BASE_DIR, "blockchain", "contract_abi.json")
    with open(abi_path, "w") as f:
        json.dump(abi, f, indent=2)
    print(f"💾  ABI saved to blockchain/contract_abi.json")

    # ── 4. Deploy ────────────────────────────────────────────────
    print("\n🚀  Deploying contract to Ganache...")
    account  = w3.eth.accounts[0]
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    tx_hash  = Contract.constructor().transact({"from": account, "gas": 3_000_000})
    receipt  = w3.eth.wait_for_transaction_receipt(tx_hash)
    address  = receipt["contractAddress"]

    # ── 5. Save address ──────────────────────────────────────────
    addr_path = os.path.join(BASE_DIR, "blockchain", "contract_address.txt")
    with open(addr_path, "w") as f:
        f.write(address)

    print(f"\n✅  CONTRACT DEPLOYED!")
    print(f"    Address:   {address}")
    print(f"    TX Hash:   {receipt['transactionHash'].hex()}")
    print(f"    Gas used:  {receipt['gasUsed']:,}")
    print("\n🎉  Ready!  Now run:  run.bat\n")


if __name__ == "__main__":
    deploy()

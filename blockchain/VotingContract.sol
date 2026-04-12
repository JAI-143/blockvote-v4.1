// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title Blockchain Voting System
/// @notice Immutable, transparent, and anonymous voting on Ethereum
contract VotingSystem {

    // ─── Data Structures ──────────────────────────────────────────────────────
    struct Candidate {
        uint256 id;
        string  name;
        string  party;
        uint256 voteCount;
    }

    // ─── State Variables ──────────────────────────────────────────────────────
    address public admin;
    bool    public votingOpen;
    uint256 public candidateCount;

    mapping(uint256 => Candidate) public candidates;
    mapping(bytes32 => bool)      public hasVoted;      // voterHash => voted?
    mapping(bytes32 => uint256)   public voterChoice;   // voterHash => candidateId

    // ─── Events ───────────────────────────────────────────────────────────────
    event VoteCast(bytes32 indexed voterHash, uint256 indexed candidateId, uint256 timestamp);
    event VotingStatusChanged(bool isOpen);
    event CandidateAdded(uint256 indexed id, string name, string party);

    // ─── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyAdmin() {
        require(msg.sender == admin, "Only admin can call this");
        _;
    }

    modifier votingIsOpen() {
        require(votingOpen, "Voting is currently closed");
        _;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────
    constructor() {
        admin      = msg.sender;
        votingOpen = true;

        // Add default candidates for demo
        _addCandidate("Alice Johnson",   "Progressive Party");
        _addCandidate("Bob Smith",       "Liberty Party");
        _addCandidate("Carol Williams",  "Unity Party");
    }

    // ─── Internal ─────────────────────────────────────────────────────────────
    function _addCandidate(string memory _name, string memory _party) internal {
        candidateCount++;
        candidates[candidateCount] = Candidate(candidateCount, _name, _party, 0);
        emit CandidateAdded(candidateCount, _name, _party);
    }

    // ─── Public Functions ─────────────────────────────────────────────────────

    /// @notice Cast a vote. voterHash is sha256(blockchainId) — fully anonymous.
    function castVote(bytes32 _voterHash, uint256 _candidateId)
        external
        votingIsOpen
    {
        require(!hasVoted[_voterHash],                              "Voter has already voted");
        require(_candidateId >= 1 && _candidateId <= candidateCount, "Invalid candidate ID");

        hasVoted[_voterHash]    = true;
        voterChoice[_voterHash] = _candidateId;
        candidates[_candidateId].voteCount++;

        emit VoteCast(_voterHash, _candidateId, block.timestamp);
    }

    /// @notice Get candidate info by ID
    function getCandidate(uint256 _id)
        external view
        returns (uint256, string memory, string memory, uint256)
    {
        Candidate memory c = candidates[_id];
        return (c.id, c.name, c.party, c.voteCount);
    }

    /// @notice Get total number of votes cast
    function getTotalVotes() external view returns (uint256 total) {
        for (uint256 i = 1; i <= candidateCount; i++) {
            total += candidates[i].voteCount;
        }
    }

    /// @notice Admin: open or close voting
    function toggleVoting() external onlyAdmin {
        votingOpen = !votingOpen;
        emit VotingStatusChanged(votingOpen);
    }

    /// @notice Admin: add a new candidate (before voting starts)
    function addCandidate(string memory _name, string memory _party)
        external onlyAdmin
    {
        _addCandidate(_name, _party);
    }
}

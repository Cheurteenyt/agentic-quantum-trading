import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StateManager:
    """State persistence with SQLite for crash recovery"""
    
    def __init__(self, db_path: str = None):
        """Initialize state manager with optional custom db path"""
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), "..", "data", "state.db"
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        logger.info(f"StateManager initialized: {self.db_path}")
    
    def _init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Agent state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_state (
                id TEXT PRIMARY KEY,
                state TEXT,
                updated_at TEXT,
                created_at TEXT
            )
        """)
        
        # Risk state table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)
        
        # Action history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT,
                action_data TEXT,
                timestamp TEXT
            )
        """)
        
        # Initialize with empty state if needed
        cursor.execute("SELECT COUNT(*) FROM agent_state WHERE id='current'")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO agent_state VALUES ('current', '{}', ?, ?)",
                (datetime.now().isoformat(), datetime.now().isoformat())
            )
        
        conn.commit()
        conn.close()
    
    def save_state(self, state: Dict[str, Any]):
        """Save agent state to database"""
        state["updated_at"] = datetime.now().isoformat()
        state["created_at"] = state.get("created_at", datetime.now().isoformat())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO agent_state VALUES (?, ?, ?, ?)",
            ("current", json.dumps(state), state["updated_at"], state["created_at"])
        )
        conn.commit()
        conn.close()
        
        logger.info(f"State saved: {len(json.dumps(state))} bytes")
    
    def load_state(self) -> Dict[str, Any]:
        """Load current agent state from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM agent_state WHERE id='current'")
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse state: {e}")
                return {}
        return {}
    
    def get_open_positions(self, state: Optional[Dict[str, Any]] = None) -> list:
        """Get currently open positions"""
        if not state:
            state = self.load_state()
        
        positions = state.get("open_positions", [])
        return [p for p in positions if not p.get("closed", False)]
    
    def save_risk_state(self, state: Dict[str, Any]):
        """Save risk-related state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for key, value in state.items():
            cursor.execute(
                "INSERT OR REPLACE INTO risk_state VALUES (?, ?, ?)",
                (key, json.dumps(value), datetime.now().isoformat())
            )
        
        conn.commit()
        conn.close()
    
    def load_risk_state(self) -> Dict[str, Any]:
        """Load risk-related state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM risk_state")
        risk_state = {}
        for key, value in cursor.fetchall():
            try:
                risk_state[key] = json.loads(value)
            except json.JSONDecodeError:
                risk_state[key] = value
        conn.close()
        return risk_state
    
    def log_action(self, action_type: str, action_data: Dict[str, Any]):
        """Log action to history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO action_history VALUES (?, ?, ?, ?)",
            (
                None,  # Let SQLite auto-increment
                action_type,
                json.dumps(action_data),
                datetime.now().isoformat()
            )
        )
        conn.commit()
        conn.close()
    
    def get_last_action(self) -> Optional[Dict[str, Any]]:
        """Get the most recent action"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action_data FROM action_history ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            return json.loads(row[0])
        return None
    
    def reset_daily_stats(self):
        """Reset daily statistics (for new trading day)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear daily stats — types préservés (FIX lot1 F10 : '{}' cassait
        # le contrat float/int et aurait explosé risk_guard à la lecture)
        cursor.execute(
            "UPDATE risk_state SET value = '0.0', updated_at = ? "
            "WHERE key = 'daily_pnl'",
            (datetime.now().isoformat(),)
        )
        cursor.execute(
            "UPDATE risk_state SET value = '0', updated_at = ? "
            "WHERE key = 'daily_trades'",
            (datetime.now().isoformat(),)
        )
        
        conn.commit()
        conn.close()
    
    def get_trading_session_count(self) -> int:
        """Count number of trading sessions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM action_history")
        count = cursor.fetchone()[0]
        conn.close()
        return count

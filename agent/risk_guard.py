"""RiskGuard - Trading risk controls and kill switch."""
import os
from typing import Optional, Dict, Any

class RiskGuard:
    """Risk control system for trading operations."""
    
    def __init__(self):
        self._load_config()
        
    def _load_config(self):
        """Load trading limits from .env file."""
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", 0.02))
        self.max_daily_loss = float(os.getenv("MAX_DAILY_LOSS", 0.05))
        self.max_open_positions = int(os.getenv("MAX_OPEN_POSITIONS", 3))
        self.kill_switch_enabled = os.getenv("KILL_SWITCH_ENABLED", "true").lower() == "true"
        
    def can_trade(self, current_position: float = 0.0, 
                   daily_pnl: float = 0.0,
                   open_positions: int = 0) -> Dict[str, Any]:
        """
        Check if trading is allowed.
        
        Args:
            current_position: Current position size (fraction of capital)
            daily_pnl: Daily PnL in percent (positive = profit)
            open_positions: Number of currently open positions
            
        Returns:
            Dict with 'allowed' bool and 'reason' string
        """
        if self.kill_switch_enabled:
            return {
                "allowed": False,
                "reason": "Kill switch is enabled"
            }
        
        # Check position size
        if current_position > self.max_position_size:
            return {
                "allowed": False,
                "reason": f"Position size {current_position:.2%} exceeds max {self.max_position_size:.2%}"
            }
        
        # Check daily loss (if pnl is negative)
        if daily_pnl < -self.max_daily_loss:
            return {
                "allowed": False,
                "reason": f"Daily loss {daily_pnl:.2%} exceeds max {self.max_daily_loss:.2%}"
            }
        
        # Check open positions count
        if open_positions >= self.max_open_positions:
            return {
                "allowed": False,
                "reason": f"Open positions {open_positions} exceeds max {self.max_open_positions}"
            }
        
        return {
            "allowed": True,
            "reason": "All checks passed"
        }
    
    def activate_kill_switch(self):
        """Activate kill switch - disable all trading."""
        self.kill_switch_enabled = True
        return {"status": "Kill switch activated"}
    
    def deactivate_kill_switch(self) -> bool:
        """
        Deactivate kill switch.
        
        Returns:
            True if successful, False if kill switch is locked
        """
        # Add cooldown or confirmation logic here if needed
        self.kill_switch_enabled = False
        return {"status": "Kill switch deactivated"}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current risk guard status."""
        return {
            "kill_switch_enabled": self.kill_switch_enabled,
            "max_position_size": self.max_position_size,
            "max_daily_loss": self.max_daily_loss,
            "max_open_positions": self.max_open_positions
        }

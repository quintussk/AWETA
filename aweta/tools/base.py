"""Base class for all tools in the AWETA toolbox."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseTool(ABC):
    """Abstract base class for all tools in the AWETA toolbox.
    
    This class provides a common interface for all tools and ensures
    consistent behavior across different tool implementations.
    
    Subclasses should implement:
    - get_name(): Return the display name of the tool
    - get_description(): Return a description of the tool
    - create_item(): Create and return the graphics item for this tool
    - get_settings_dialog(): Return a settings dialog widget
    - serialize(): Convert tool state to dictionary for saving
    - deserialize(): Restore tool state from dictionary
    
    Attributes:
        tool_id: Unique identifier for this tool instance
        label: Display label for this tool instance
    """
    
    def __init__(self, tool_id: int, label: str = ""):
        """Initialize a tool instance.
        
        Args:
            tool_id: Unique identifier for this tool instance
            label: Display label for this tool instance
        """
        self.tool_id = tool_id
        self.label = label or self.get_default_label()
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the display name of this tool type.
        
        Returns:
            Tool name (e.g., "Belt", "Exit", "Sensor")
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Return a description of what this tool does.
        
        Returns:
            Tool description
        """
        pass
    
    @abstractmethod
    def get_default_label(self) -> str:
        """Return the default label for a new instance.
        
        Returns:
            Default label string
        """
        pass
    
    @abstractmethod
    def create_item(self, x: float, y: float, **kwargs) -> Any:
        """Create and return the graphics item for this tool.
        
        Args:
            x: X position for the item
            y: Y position for the item
            **kwargs: Additional parameters specific to the tool
            
        Returns:
            Graphics item (e.g., QGraphicsRectItem, QGraphicsPathItem)
        """
        pass
    
    @abstractmethod
    def get_settings_dialog(self, parent: Any, item: Any) -> Any:
        """Create and return a settings dialog for this tool.
        
        Args:
            parent: Parent widget for the dialog
            item: The graphics item to configure
            
        Returns:
            Dialog widget (e.g., QDialog)
        """
        pass
    
    def serialize(self) -> Dict[str, Any]:
        """Convert tool state to dictionary for saving.
        
        Returns:
            Dictionary containing tool state
        """
        return {
            "tool_type": self.get_name(),
            "tool_id": self.tool_id,
            "label": self.label,
        }
    
    def deserialize(self, data: Dict[str, Any]) -> None:
        """Restore tool state from dictionary.
        
        Args:
            data: Dictionary containing tool state
        """
        self.tool_id = data.get("tool_id", self.tool_id)
        self.label = data.get("label", self.label)
    
    def __repr__(self) -> str:
        """Return string representation of the tool."""
        return f"{self.__class__.__name__}(id={self.tool_id}, label={self.label!r})"


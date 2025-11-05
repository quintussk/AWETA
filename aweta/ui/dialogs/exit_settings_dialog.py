"""Settings dialog for exit block configuration."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QLabel,
    QDialogButtonBox,
    QComboBox,
)

from aweta.core.variables import VARS
from aweta.tools.belt.exit_item import ExitBlock


class ExitSettingsDialog(QDialog):
    """Dialog for configuring exit block settings."""
    
    def __init__(self, parent, exit_block: ExitBlock):
        """Initialize exit settings dialog.
        
        Args:
            parent: Parent widget
            exit_block: Exit block item to configure
        """
        super().__init__(parent)
        self.setWindowTitle("Exit instellingen")
        self.exit_block = exit_block
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # Title
        self.le_title = QLineEdit(exit_block.label, self)
        
        # Capacity
        self.sb_capacity = QSpinBox(self)
        self.sb_capacity.setRange(0, 999)
        self.sb_capacity.setValue(int(getattr(exit_block, 'capacity', 3)))
        
        # Dwell time
        self.sb_dwell = QSpinBox(self)
        self.sb_dwell.setRange(0, 600000)
        self.sb_dwell.setSingleStep(100)
        self.sb_dwell.setSuffix(" ms")
        self.sb_dwell.setValue(int(getattr(exit_block, 'dwell_ms', 2000)))
        
        # Variable inputs via MainWindow helpers
        wnd = self.window()
        make_var_input = getattr(wnd, '_make_var_input', None)
        get_var_value = getattr(wnd, '_get_var_value', None)
        
        # FT In
        self.cb_ft_in = QCheckBox("FT In aanwezig", self)
        self.cb_ft_in.setChecked(getattr(exit_block, 'ft_in_enabled', False))
        if callable(make_var_input):
            self.le_ft_in = make_var_input(self, getattr(exit_block, 'ft_in_var', '') or None)
        else:
            self.le_ft_in = QLineEdit(getattr(exit_block, 'ft_in_var', '') or '', self)
        self.le_ft_in.setEnabled(self.cb_ft_in.isChecked())
        
        # FT Out
        self.cb_ft_out = QCheckBox("FT Out aanwezig", self)
        self.cb_ft_out.setChecked(getattr(exit_block, 'ft_out_enabled', False))
        if callable(make_var_input):
            self.le_ft_out = make_var_input(self, getattr(exit_block, 'ft_out_var', '') or None)
        else:
            self.le_ft_out = QLineEdit(getattr(exit_block, 'ft_out_var', '') or '', self)
        self.le_ft_out.setEnabled(self.cb_ft_out.isChecked())
        
        # Connect signals
        self.cb_ft_in.toggled.connect(self.le_ft_in.setEnabled)
        self.cb_ft_out.toggled.connect(self.le_ft_out.setEnabled)
        
        # Add to form
        form.addRow(QLabel("Titel:"), self.le_title)
        form.addRow(QLabel("Capaciteit:"), self.sb_capacity)
        form.addRow(QLabel("Dwell tijd:"), self.sb_dwell)
        form.addRow(self.cb_ft_in)
        form.addRow(QLabel("FT In variabele:"), self.le_ft_in)
        form.addRow(self.cb_ft_out)
        form.addRow(QLabel("FT Out variabele:"), self.le_ft_out)
        layout.addLayout(form)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        layout.addWidget(buttons)
        
        # Store helper function
        self.get_var_value = get_var_value
        
        # Connect signals
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
    
    def _on_ok(self):
        """Handle OK button click."""
        wnd = self.window()
        get_var_value = getattr(wnd, '_get_var_value', None)
        
        self.exit_block.set_label(self.le_title.text().strip() or self.exit_block.label)
        self.exit_block.apply_capacity(int(self.sb_capacity.value()))
        self.exit_block.dwell_ms = int(self.sb_dwell.value())
        self.exit_block._update_timer_text()
        
        self.exit_block.set_sensors_enabled(self.cb_ft_in.isChecked(), self.cb_ft_out.isChecked())
        
        if callable(get_var_value):
            self.exit_block.ft_in_var = get_var_value(self.le_ft_in)
            self.exit_block.ft_out_var = get_var_value(self.le_ft_out)
        else:
            self.exit_block.ft_in_var = (self.le_ft_in.text().strip() or None)
            self.exit_block.ft_out_var = (self.le_ft_out.text().strip() or None)
        
        for var in (self.exit_block.ft_in_var, self.exit_block.ft_out_var):
            if var and var not in VARS:
                VARS[var] = False
        
        self.exit_block.update_sensor_visual()
        self.accept()


"""Settings dialog for belt configuration."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QLabel,
    QDialogButtonBox,
    QPushButton,
    QComboBox,
)

from aweta.core.constants import TICK_PX
from aweta.core.variables import VARS
from aweta.tools.belt.belt_item import Belt


class BeltSettingsDialog(QDialog):
    """Dialog for configuring belt settings."""
    
    def __init__(self, parent, belt: Belt):
        """Initialize belt settings dialog.
        
        Args:
            parent: Parent widget
            belt: Belt item to configure
        """
        super().__init__(parent)
        self.setWindowTitle("Band instellingen")
        self.belt = belt
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # Title
        self.le_title = QLineEdit(belt.label, self)
        
        # Width in ticks
        self.sb_ticks = QSpinBox(self)
        self.sb_ticks.setRange(1, 100)
        self.sb_ticks.setValue(belt.width_ticks)
        
        # Variable inputs via MainWindow helpers (fallback to QLineEdit if absent)
        wnd = self.window()
        make_var_input = getattr(wnd, '_make_var_input', None)
        get_var_value = getattr(wnd, '_get_var_value', None)
        
        if callable(make_var_input):
            self.le_motor = make_var_input(self, belt.motor_var)
        else:
            self.le_motor = QLineEdit(belt.motor_var or "", self)
        
        # FT In
        self.cb_ft_in = QCheckBox("FT In aanwezig", self)
        self.cb_ft_in.setChecked(getattr(belt, 'ft_in_enabled', False))
        if callable(make_var_input):
            self.le_ft_in = make_var_input(self, getattr(belt, 'ft_in_var', '') or None)
        else:
            self.le_ft_in = QLineEdit(getattr(belt, 'ft_in_var', '') or '', self)
        self.le_ft_in.setEnabled(self.cb_ft_in.isChecked())
        
        # FT Out
        self.cb_ft_out = QCheckBox("FT Out aanwezig", self)
        self.cb_ft_out.setChecked(getattr(belt, 'ft_out_enabled', False))
        if callable(make_var_input):
            self.le_ft_out = make_var_input(self, getattr(belt, 'ft_out_var', '') or None)
        else:
            self.le_ft_out = QLineEdit(getattr(belt, 'ft_out_var', '') or '', self)
        self.le_ft_out.setEnabled(self.cb_ft_out.isChecked())
        
        # Connect signals
        self.cb_ft_in.toggled.connect(self.le_ft_in.setEnabled)
        self.cb_ft_out.toggled.connect(self.le_ft_out.setEnabled)
        
        # Add to form
        form.addRow(QLabel("Titel:"), self.le_title)
        form.addRow(QLabel("Breedte (ticks):"), self.sb_ticks)
        form.addRow(QLabel("Motor variabele:"), self.le_motor)
        form.addRow(self.cb_ft_in)
        form.addRow(QLabel("FT In variabele:"), self.le_ft_in)
        form.addRow(self.cb_ft_out)
        form.addRow(QLabel("FT Out variabele:"), self.le_ft_out)
        layout.addLayout(form)
        
        # Test sensor button
        btn_test = QPushButton("Test sensor puls", self)
        layout.addWidget(btn_test)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        layout.addWidget(buttons)
        
        # Store helper functions
        self.get_var_value = get_var_value
        
        # Connect signals
        btn_test.clicked.connect(self._on_test)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
    
    def _on_ok(self):
        """Handle OK button click."""
        wnd = self.window()
        get_var_value = getattr(wnd, '_get_var_value', None)
        
        self.belt.set_label(self.le_title.text().strip() or self.belt.label)
        self.belt.resize_for_ticks(self.sb_ticks.value())
        
        if callable(get_var_value):
            self.belt.motor_var = get_var_value(self.le_motor)
        else:
            self.belt.motor_var = (self.le_motor.text().strip() or None)
        
        if self.belt.motor_var and self.belt.motor_var not in VARS:
            VARS[self.belt.motor_var] = False
        
        self.belt.set_sensors_enabled(self.cb_ft_in.isChecked(), self.cb_ft_out.isChecked())
        
        if callable(get_var_value):
            self.belt.ft_in_var = get_var_value(self.le_ft_in)
            self.belt.ft_out_var = get_var_value(self.le_ft_out)
        else:
            self.belt.ft_in_var = (self.le_ft_in.text().strip() or None)
            self.belt.ft_out_var = (self.le_ft_out.text().strip() or None)
        
        for var in (self.belt.ft_in_var, self.belt.ft_out_var):
            if var and var not in VARS:
                VARS[var] = False
        
        self.belt.update_sensor_visual()
        self.accept()
    
    def _on_test(self):
        """Handle test sensor button click."""
        # Quick pulse for 300 ms for FT In and FT Out if enabled
        if self.belt.ft_in_enabled:
            self.belt.ft_in_state = True
            if self.belt.ft_in_var:
                VARS[self.belt.ft_in_var] = True
        
        if self.belt.ft_out_enabled:
            self.belt.ft_out_state = True
            if self.belt.ft_out_var:
                VARS[self.belt.ft_out_var] = True
        
        self.belt.update_sensor_visual()
        
        def _sensor_off():
            if self.belt.ft_in_enabled:
                self.belt.ft_in_state = False
                if self.belt.ft_in_var:
                    VARS[self.belt.ft_in_var] = False
            if self.belt.ft_out_enabled:
                self.belt.ft_out_state = False
                if self.belt.ft_out_var:
                    VARS[self.belt.ft_out_var] = False
            self.belt.update_sensor_visual()
        
        QTimer.singleShot(300, _sensor_off)


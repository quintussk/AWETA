# Refactoring Notes - AWETA Project

## Nieuwe Structuur

Het project is volledig herstructureerd voor betere schaalbaarheid en onderhoudbaarheid.

### Nieuwe Mappenstructuur

```
aweta/
├── core/              # Core functionaliteit (constants, variables)
│   ├── __init__.py
│   ├── constants.py
│   └── variables.py
├── tools/             # Toolbox met alle tools
│   ├── __init__.py
│   ├── base.py        # BaseTool class voor alle tools
│   └── belt/          # Belt tool module
│       ├── __init__.py
│       ├── belt_item.py
│       ├── exit_item.py
│       ├── box_generator.py
│       ├── port.py
│       └── link.py
├── ui/                # UI components (nog te implementeren)
│   ├── view.py        # View class met simulation logic
│   ├── main_window.py # MainWindow class
│   └── dialogs/       # Dialog widgets
├── plc/               # PLC connectiviteit
│   ├── __init__.py
│   ├── connection.py
│   └── db_viewer.py
└── project/           # Project management
    ├── __init__.py
    └── manager.py
```

### Wat is veranderd

1. **Core Module**: 
   - `constants.py` - Alle constanten (TICK_PX, PORT_R)
   - `variables.py` - Globale VARS dictionary

2. **Tools Module**:
   - `base.py` - Abstracte BaseTool class voor toekomstige tools
   - `belt/` - Complete belt tool implementatie
     - Belt, ExitBlock, BoxGenerator, Port, Link classes

3. **PLC Module**:
   - `connection.py` - PLCConnection class voor snap7 connectiviteit
   - `db_viewer.py` - DBViewer dialog voor DB viewing

4. **Project Module**:
   - `manager.py` - ProjectManager voor save/load functionaliteit

### Nog te implementeren

- `aweta/ui/view.py` - View class met alle simulation logic (uit main.py regels 572-1407)
- `aweta/ui/main_window.py` - MainWindow class (uit main.py regels 1409-2023)
- `aweta/ui/dialogs/` - Dialogs (ToolboxDialog, settings dialogs, etc.)

### Volgende stappen

1. View class uitpakken naar `aweta/ui/view.py`
2. MainWindow class uitpakken naar `aweta/ui/main_window.py`
3. Dialogs uitpakken naar `aweta/ui/dialogs/`
4. Nieuwe `main.py` maken die alles importeert
5. Onnodige bestanden verwijderen (container.py, containers.py)

### Voordelen nieuwe structuur

- **Schaalbaar**: Nieuwe tools kunnen eenvoudig worden toegevoegd door BaseTool te subclassen
- **Modulair**: Elke module heeft een duidelijke verantwoordelijkheid
- **Onderhoudbaar**: Code is beter georganiseerd en makkelijker te vinden
- **Testbaar**: Modules kunnen onafhankelijk worden getest
- **Uitbreidbaar**: Klaar voor 10+ tools in de toekomst


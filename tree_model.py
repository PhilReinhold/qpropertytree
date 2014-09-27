from PyQt4.QtCore import Qt, QTimer, QPoint, pyqtWrapperType
from PyQt4.QtGui import QStandardItem, QAction, QTreeView, QMenu, QStandardItemModel, QApplication, QTableView, \
    QItemDelegate, QDoubleSpinBox, QMainWindow, QDockWidget, QComboBox


def increment_name(base_name, existing):
    i = 1
    while base_name[-i:].isdigit():
        i += 1
    if i == 1:
        n = 1
        name = base_name
    else:
        n = int(base_name[-(i-1):])
        name = base_name[:-(i-1)]
    while name + str(n) in existing:
        n += 1
    return name + str(n)


class PropItem(QStandardItem):

    def get(self):
        return self.text()

    def set(self, value):
        self.setText(value)

    def clone(self):
        return type(self)(self.get())

    def encode(self):
        return self.get()

    def decode(self, value):
        self.set(value)


class MetaTreeObject(pyqtWrapperType):

    def __new__(cls, name, parents, dct):
        new_dct = dct.copy()
        new_dct["_props"] = _props = {}
        for key, val in dct.items():
            if isinstance(val, PropItem):
                def getter(self):
                    self._prop_items[key].get()

                def setter(self, value):
                    self._prop_items[key].set(value)

                def cloner():
                    val.clone()

                new_dct[key] = property(getter, setter)
                _props[key] = cloner

        return super(MetaTreeObject, cls).__new__(cls, name, parents, new_dct)


class TreeObject(QStandardItem):
    __metaclass__ = MetaTreeObject
    standard_name = "TreeObject"
    child_classes = []

    def __init__(self, parent=None):
        super(TreeObject, self).__init__()
        if parent:
            self.name = increment_name(self.standard_name, parent.child_names())
        else:
            self.name = self.standard_name
        self.setText(self.name)
        self.context_menu = QMenu()
        for cls in self.child_classes:
            action = QAction("Insert " + cls.standard_name, self.context_menu)
            action.triggered.connect(lambda _, c=cls: self.appendRow(c(self)))
            self.context_menu.addAction(action)

        clone_action = QAction("Clone", self.context_menu)
        self.context_menu.addAction(clone_action)
        clone_action.triggered.connect(self.clone)

        self.props_table = PropsTable()
        self.props_widget = PropsWidget(self.props_table)

        self._prop_items = {}
        for name, factory in self._props.items():
            self._prop_items[name] = prop_item = factory()
            self.props_table.add_prop(name, prop_item)

    def children(self):
        return [self.child(n) for n in range(self.rowCount())]

    def child_names(self):
        return [c.name for c in self.children()]

    def encode(self):
        return {
            'text': str(self.text()),
            'children': [
                (c.__class__.__name__, c.__module__, c.encode())
                for c in self.children()
            ],
            'props': self.props_table.encode()
        }

    def decode(self, d):
        child_names = [
            c.name for c in self.parent_or_model().children() if c is not self
        ]
        self.setText(increment_name(d['text'], child_names))
        self.props_table.decode(d['props'])
        for class_name, module_name, child_dict in d['children']:
            module = __import__(module_name)
            cls = getattr(module, class_name)
            inst = cls(self.parent())
            self.appendRow(inst)
            inst.decode(child_dict)

    def parent_or_model(self):
        if self.parent() is None:
            return self.model()
        return self.parent()

    def clone(self):
        d = self.encode()
        new_inst = type(self)(self.parent())
        self.parent_or_model().appendRow(new_inst)
        new_inst.decode(d)


class PropsTable(QStandardItemModel):

    def __init__(self):
        super(PropsTable, self).__init__()
        self._items_dict = {}

    def flags(self, idx):
        sflags = super(PropsTable, self).flags(idx)
        if idx.column() == 0:
            return sflags & ~Qt.ItemIsEditable
        return sflags

    def add_prop(self, name, item):
        self.appendRow([QStandardItem(name), item])
        self._items_dict[name] = item

    def encode(self):
        return {name: item.encode() for name, item in self._items_dict.items()}

    def decode(self, d):
        for name, value in d.items():
            self._items_dict[name].decode(value)


class PropsWidget(QTableView):

    def __init__(self, model):
        super(PropsWidget, self).__init__()
        self.setModel(model)
        self.setItemDelegate(PropDelegate(model))


class FloatProp(PropItem):

    def __init__(self, init):
        super(FloatProp, self).__init__(str(init))

    def create_editor(self):
        w = QDoubleSpinBox()
        w.setValue(float(self.text()))
        return w

    def set_data(self, widget):
        """
        :type widget: QDoubleSpinBox
        """
        self.setText(str(widget.value()))

    def get(self):
        return float(self.text())

    def set(self, val):
        self.setText(str(val))


class ObjectProp(PropItem):

    def __init__(self, cls_or_item):
        if isinstance(cls_or_item, TreeObject):
            super(ObjectProp, self).__init__(cls_or_item.name)
            self.object_class = type(cls_or_item)
            self.current_item = cls_or_item
        else:
            super(ObjectProp, self).__init__("None")
            self.object_class = cls_or_item
            self.current_item = None

    def set_parent_instance(self, parent):
        self.parent_instance = parent
        pv = self.potential_values()
        if pv:
            self.set(pv[0])

    def potential_values(self):
        return [o for o in self.parent_instance.children()
                if isinstance(o, self.object_class)]

    def create_editor(self):
        w = QComboBox()
        items = self.potential_values()
        names = [o.name for o in items]
        w.addItems(names)
        if self.current_item is not None and self.current_item.name in names:
            w.setCurrentIndex(names.index(self.current_item.name))
        return w

    def set_data(self, widget):
        """
        :type widget: QComboBox
        """
        name = widget.currentText()
        self.set(self.item_from_name(name))

    def get(self):
        return self.current_item

    def set(self, item):
        self.current_item = item
        if item is None:
            self.setText("None")
        else:
            self.setText(item.name)

    def encode(self):
        item = self.current_item
        item_name = item.name if item is not None else None
        return (
            item_name,
            self.object_class.__name__,
            self.object_class.__module__
        )

    def decode(self, val):
        item_name, class_name, module_name = val
        module = __import__(module_name)
        self.object_class = getattr(module, class_name)
        if item_name is not None:
            self.set(self.item_from_name(item_name))

    def item_from_name(self, name):
        for item in self.potential_values():
            if item.name == name:
                return item

    def clone(self):
        if self.current_item is None:
            return ObjectProp(self.object_class)
        else:
            return ObjectProp(self.current_item)


class PropDelegate(QItemDelegate):

    def __init__(self, model):
        super(PropDelegate, self).__init__()
        self.model = model

    def createEditor(self, widget, style, idx):
        item = self.model.itemFromIndex(idx)
        w = item.create_editor()
        w.setParent(widget)
        return w

    def setModelData(self, widget, model, index):
        model.itemFromIndex(index).set_data(widget)


class TreeModel(QStandardItemModel):

    def children(self):
        return [self.item(n, 0) for n in range(self.rowCount())]

    def child_names(self):
        return [c.name for c in self.children()]


class TreeWidget(QTreeView):

    def __init__(self, **kwargs):
        super(TreeWidget, self).__init__(**kwargs)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.popup_context_menu)

    def popup_context_menu(self, pos):
        item = self.model().itemFromIndex(self.indexAt(pos))
        if item:
            item.context_menu.exec_(self.mapToGlobal(pos) + QPoint(0, 23))
            return True
        return False

    def setModel(self, model):
        super(TreeWidget, self).setModel(model)
        model.rowsInserted.connect(lambda parent, i, j: self.expand(parent))


class MainWindow(QMainWindow):

    def __init__(self, model):
        super(MainWindow, self).__init__()
        self.tree_dock = QDockWidget()
        self.props_dock = QDockWidget()
        self.tree_view = TreeWidget()
        self.tree_view.setModel(model)
        self.tree_dock.setWidget(self.tree_view)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.tree_dock)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.props_dock)

        self.tree_view.clicked.connect(self.change_props_widget)

    def change_props_widget(self, idx):
        self.props_dock.setWidget(
            self.tree_view.model().itemFromIndex(idx).props_widget
        )


if __name__ == '__main__':
    class C(TreeObject):
        standard_name = "C"

    class B(TreeObject):
        standard_name = "B"
        test_float = FloatProp(3.3)
        test_object = ObjectProp(C)

        def __init__(self, parent):
            super(B, self).__init__(parent)
            print self.test_float
            self.test_float = 4.4
            print self.test_float
            self._prop_items['test_object'].set_parent_instance(parent)

    class A(TreeObject):
        standard_name = "A"
        child_classes = [B, C]

    app = QApplication([])
    model = TreeModel()
    root1 = A(model)
    model.appendRow(root1)
    widget = MainWindow(model)
    widget.show()
    timer = QTimer()
    timer.singleShot(1, lambda: widget.raise_())
    app.exec_()

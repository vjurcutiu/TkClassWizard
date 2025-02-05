from typing import get_args, get_origin, Iterable, Union, Literal, Any, TYPE_CHECKING, TypeVar
from abc import ABC
from inspect import isabstract
from contextlib import suppress

from ..convert import *
from ..aliasing import *
from ..dpi import *
from ..utilities import *
from ..storage import *
from ..messagebox import Messagebox
from ..extensions import extendable
from ..doc import doc_category

import tkinter.ttk as ttk
import tkinter as tk
import json


if TYPE_CHECKING:
    from .window import ObjectEditWindow


T = TypeVar('T')


__all__ = (
    "NewObjectFrameBase",
)


@extendable
@doc_category("Object frames")
class NewObjectFrameBase(ttk.Frame):
    """
    Base Frame for inside the :class:`ObjectEditWindow` that allows object definition.

    Parameters
    -------------
    class_: Any
        The class we are defining for.
    return_widget: Any
        The widget to insert the ObjectInfo into after saving.
    parent: TopLevel
        The parent window.
    old_data: Any
        The old_data gui data.
    check_parameters: bool
        Check parameters (by creating the real object) upon saving.
        This is ignored if editing a function instead of a class.
    allow_save: bool
        If False, will open in read-only mode.
    """
    origin_window: "ObjectEditWindow" = None

    def __init__(
        self,
        class_: Any,
        return_widget: Union[ComboBoxObjects, ListBoxObjects, None],
        parent = None,
        old_data: Any = None,
        check_parameters: bool = True,
        allow_save = True,
    ):
        self.class_ = class_
        "The type (class) of object being creating"

        self.return_widget = return_widget
        "The widget where the abstract object (ObjectInfo) will be stored"

        self._original_gui_data = None
        self.parent = parent
        self.check_parameters = check_parameters  # At save time
        "Check for parameters on save"

        self.allow_save = allow_save  # Allow save or not allow (eg. viewing SQL data)
        "Saving is allowed"

        self.old_gui_data = old_data  # Set in .load
        "If editing, the value being edited"

        # If return_widget is None, it's a floating display with no return value
        editing_index = return_widget.current() if return_widget is not None else -1
        if editing_index == -1:
            editing_index = None

        self.editing_index = editing_index
        "The index of object being edited"

        super().__init__(master=parent)
        self.init_toolbar_frame(class_)
        self.init_main_frame()

    @staticmethod
    def get_cls_name(cls: T) -> Union[str, T]:
        """
        Returns the name of the class ``cls`` or
        the original class when the name cannot be obtained.
        If alias exists, alias is returned instead.
        """
        name = NewObjectFrameBase._get_cls_unaliased_name(cls)
        if (alias := get_aliased_name(cls)) is not None:
            return alias + f" ({name})"
        
        return name

    @staticmethod
    def _get_cls_unaliased_name(cls: T) -> Union[str, T]:
        """
        Returns the name of the class ``cls`` or
        the original class when the name cannot be obtained.
        """
        if hasattr(cls, "__name__"):
            return cls.__name__
        if hasattr(cls, "_name"):
            return cls._name

        return cls

    @classmethod
    def set_origin_window(cls, window: "ObjectEditWindow"):
        cls.origin_window = window

    @classmethod
    def cast_type(cls, value: Any, types: Iterable):
        """
        Tries to convert *value* into one of the types inside *types* (first successful).

        Raises
        ----------
        TypeError
            Could not convert into any type.
        """

        CAST_FUNTIONS = {
            dict: lambda v: convert_to_object_info(json.loads(v))
        }

        # Validate literals
        if get_origin(types[0]) is Literal:
            if value not in (args := get_args(types[0])):
                raise ValueError(f"'{value}' is not a valid value'. Accepted: {args}")
            
            return value

        for type_ in filter(lambda t: cls._get_cls_unaliased_name(t) in __builtins__, types):
            with suppress(Exception):
                cast_funct = CAST_FUNTIONS.get(type_)
                if cast_funct is None:
                    value = type_(value)
                else:
                    value = cast_funct(value)
                break
        else:
            raise TypeError(f"Could not convert '{value}' to any of accepted types.\nAccepted types: '{types}'")

        return value

    @classmethod
    def convert_types(cls, types_in):
        """
        Type preprocessing method, that extends the list of types with inherited members (polymorphism)
        and removes classes that are wrapped by some other class, if the wrapper class also appears in
        the annotations.
        """
        def remove_classes(types: list):
            r = types.copy()
            for type_ in types:
                # It's a wrapper of some class -> remove the wrapped class
                if hasattr(type_, "__wrapped__"):
                    if type_.__wrapped__ in r:
                        r.remove(type_.__wrapped__)

                # Abstract classes are classes that don't allow instantiation -> remove the class
                if isabstract(type_):
                    r.remove(type_)

            return r

        while get_origin(types_in) is Union:
            types_in = get_args(types_in)

        if not isinstance(types_in, list):
            if isinstance(types_in, tuple):
                types_in = list(types_in)
            else:
                types_in = [types_in, ]

        # Also include inherited objects
        subtypes = []
        for t in types_in:
            if cls.get_cls_name(t) in __builtins__:
                continue  # Don't consider built-int types for polymorphism

            if hasattr(t, "__subclasses__"):
                for st in t.__subclasses__():
                    subtypes.extend(cls.convert_types(st))

        # Remove wrapped classes (eg. wrapped by decorator) + ABC classes
        return remove_classes(types_in + subtypes)

    def init_main_frame(self):
        frame_main = ttk.Frame(self)
        frame_main.pack(expand=True, fill=tk.BOTH)
        self.frame_main = frame_main

    def init_toolbar_frame(self, class_):
        frame_toolbar = ttk.Frame(self)
        frame_toolbar.pack(fill=tk.X)
        self.frame_toolbar = frame_toolbar

    @property
    def modified(self) -> bool:
        """
        Returns True if the GUI values have been modified.
        """
        current_values = self.get_gui_data()
        return current_values != self._original_gui_data

    def update_window_title(self):
        "Set's the window title according to edit context."
        self.origin_window.title(f"{'New' if self.old_gui_data is None else 'Edit'} {self.get_cls_name(self.class_)} object")

    def close_frame(self):
        if self.allow_save and self.modified:
            resp = Messagebox.yesnocancel("Save?", "Do you wish to save?", master=self.origin_window)
            if resp is not None:
                if resp:
                    self.save()
                else:
                    self._cleanup()
        else:
            self._cleanup()

    def new_object_frame(
        self,
        class_,
        widget,
        *args,
        **kwargs
    ):
        """
        Opens up a new object frame on top of the current one.
        Parameters are the same as in :class:`NewObjectFrame` (current class).
        """
        allow_save = kwargs.pop("allow_save", self.allow_save)
        return self.origin_window.open_object_edit_frame(
            class_, widget, allow_save=allow_save, *args, **kwargs
        )

    def to_object(self):
        """
        Creates an object from the GUI data.
        """
        raise NotImplementedError

    def load(self, old_data: Any):
        """
        Loads the old object info data into the GUI.

        Parameters
        -------------
        old_data: Any
            The old gui data to load.
        """
        raise NotImplementedError

    def save(self):
        """
        Save the current object into the return widget and then close this frame.
        """
        try:
            if not self.allow_save or self.return_widget is None:
                raise TypeError("Saving is not allowed in this context!")

            object_ = self.to_object()
            self._update_ret_widget(object_)
            self._cleanup()
        except Exception as exc:
            Messagebox.show_error(
                "Saving error",
                f"Could not save the object.\n{exc}",
                parent=self.origin_window
            )

    def remember_gui_data(self):
        """
        Remembers GUI data for change checking.
        """
        self._original_gui_data = self.get_gui_data()

    def get_gui_data(self) -> Any:
        """
        Returns all GUI values.
        """
        raise NotImplementedError

    def _cleanup(self):
        self.origin_window.clean_object_edit_frame()

    def _update_ret_widget(self, new: Any):
        ind = self.return_widget.count()
        if self.old_gui_data is not None:
            ret_widget = self.return_widget
            if self.editing_index is not None:  # The index of edited item inside return widget
                ind = self.editing_index
                ret_widget.delete(ind)

        self.return_widget.insert(ind, new)
        if isinstance(self.return_widget, ComboBoxObjects):
            self.return_widget.current(ind)
        else:
            self.return_widget.selection_set(ind)

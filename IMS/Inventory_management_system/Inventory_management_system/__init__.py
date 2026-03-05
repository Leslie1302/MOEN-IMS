# Python 3.14 Django Context.__copy__ Monkeypatch
import copy
from django.template import context

def _patched_base_context_copy(self):
    duplicate = object.__new__(type(self))
    duplicate.__dict__ = self.__dict__.copy()
    duplicate.dicts = self.dicts[:]
    return duplicate

def _patched_context_copy(self):
    duplicate = object.__new__(type(self))
    duplicate.__dict__ = self.__dict__.copy()
    duplicate.dicts = self.dicts[:]
    if hasattr(self, 'render_context'):
        duplicate.render_context = copy.copy(self.render_context)
    return duplicate

context.BaseContext.__copy__ = _patched_base_context_copy
context.Context.__copy__ = _patched_context_copy

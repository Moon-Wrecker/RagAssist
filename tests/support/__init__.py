"""Importable test library for RagAssist. Nothing in here is a test.

Layout (dependency direction: contracts -> ports only; nothing imports from tests/unit etc.):

* ``spec``       constants taken from the approved specs (one place to change on spec drift)
* ``settings``   hermetic ``Settings`` builder
* ``pending``    skip helpers for modules the implementation team has not landed yet
* ``defects``    registry of known defects, used to mark strict xfails
* ``assertions`` reusable domain assertions
* ``sse``        Server-Sent-Events stream parser
* ``contracts``  one abstract contract suite per port, subclassed per adapter

Fakes live in ``tests/fakes`` and builders in ``tests/factories`` (the layout AGENTS.md declares).
"""

import collections
import copy
import functools
import threading
import enum
from types import NoneType, GeneratorType
from _collections_abc import range_iterator
import random
import numpy as np
import generator_hack

import game.venator
from game.engine.gfx import TextureReference, SpriteLayer, ShapeLayer, CombinedLayer, GuiImage, Camera, TextureAtlas
from game.map.maps import MapAttrs
from game.map.tilemap import TileMap
from game.map.tileset import Tileset
from game.components.textbox import TextObj

SKIP_CLS = (
    type(threading.Lock()),
    enum.Enum,
    TextureReference,
    SpriteLayer,
    ShapeLayer,
    CombinedLayer,
    Tileset,
    TileMap,
    MapAttrs,
    GuiImage,
    Camera,
    TextObj,
    TextureAtlas,
)
PRIMITIVE_CLS = (int, float, bool, str, bytes, complex, NoneType, bytes, range, type)
CONTAINER_CLS = (list, set, tuple, frozenset, collections.deque)
DEEP_COPYABLE_CLS = (range_iterator, random.Random, np.bool_)
NO_RECORD = (
    'raw_pressed_keys',
    'original_maps_dict',
    'cheating_detected',
    'net',
    'won',
)


class Container:
    cls: type
    copy: tuple


class Object:
    inst: any
    attr: dict


class Random:
    state: any


class Generator:
    back: any


class GameBackup:
    @staticmethod
    def __generate_snapshot(obj, storage, layer):
        if isinstance(obj, DEEP_COPYABLE_CLS):
            return copy.deepcopy(obj)

        if isinstance(obj, np.ndarray):
            return np.copy(obj)

        if isinstance(obj, SKIP_CLS) or isinstance(obj, PRIMITIVE_CLS):
            return obj

        obj_id = id(obj)
        if obj_id in storage:
            return storage[obj_id]

        if isinstance(obj, GeneratorType):
            g = Generator()
            storage[obj_id] = g
            g.back = generator_hack.backup(
                obj, functools.partial(GameBackup.__generate_snapshot, storage=storage, layer=layer))
            return g

        if isinstance(obj, CONTAINER_CLS):
            c = Container()
            storage[obj_id] = c

            c.cls = type(obj)
            c.copy = tuple(GameBackup.__generate_snapshot(o, storage, layer + [(None, type(o))]) for o in obj)

            return c

        if isinstance(obj, dict):
            d = {}
            storage[obj_id] = d

            for k, v in obj.items():
                d[k] = GameBackup.__generate_snapshot(v, storage, layer + [(k, type(v))])

            return d

        assert hasattr(obj, '__dict__'), layer

        o = Object()
        o.inst = obj
        o.attr = {}
        storage[obj_id] = o

        is_venator = isinstance(obj, game.venator.Venator)
        for k in dir(obj):
            if k.startswith('__'):
                continue
            if is_venator and k in NO_RECORD:
                continue
            v = getattr(obj, k)
            if callable(v):
                continue
            o.attr[k] = GameBackup.__generate_snapshot(v, storage, layer + [(k, type(v))])

        return o

    @staticmethod
    def generate_snapshot(obj):
        storage = {}
        return GameBackup.__generate_snapshot(obj, storage, [])

    @staticmethod
    def __inflate_snapshot(snapshot, storage):
        snapshot_id = id(snapshot)
        if snapshot_id in storage:
            return storage[snapshot_id]

        if isinstance(snapshot, Generator):
            inflated = snapshot.back
            storage[snapshot_id] = inflated
            generator_hack.inflate(inflated, functools.partial(GameBackup.__inflate_snapshot, storage=storage))
            return inflated

        if isinstance(snapshot, Random):
            inflated = random.Random()
            storage[snapshot_id] = inflated
            inflated.setstate(snapshot.state)
            return inflated

        if isinstance(snapshot, Container):
            inflated = snapshot.cls((GameBackup.__inflate_snapshot(ele, storage) for ele in snapshot.copy))
            storage[snapshot_id] = inflated
            return inflated

        if isinstance(snapshot, dict):
            inflated = {}
            storage[snapshot_id] = inflated
            for k, v in snapshot.items():
                inflated[k] = GameBackup.__inflate_snapshot(v, storage)
            return inflated

        if isinstance(snapshot, Object):
            inflated = snapshot.inst
            storage[snapshot_id] = inflated
            for k, v in snapshot.attr.items():
                setattr(inflated, k, GameBackup.__inflate_snapshot(v, storage))
            return inflated

        return snapshot

    @staticmethod
    def inflate_snapshot(snapshot):
        storage = {}
        return GameBackup.__inflate_snapshot(snapshot, storage)

#include <Python.h>

struct _PyInterpreterFrame {
    PyCodeObject *f_code; /* Strong reference */
    struct _PyInterpreterFrame *previous;
    PyObject *f_funcobj; /* Strong reference. Only valid if not on C stack */
    PyObject *f_globals; /* Borrowed reference. Only valid if not on C stack */
    PyObject *f_builtins; /* Borrowed reference. Only valid if not on C stack */
    PyObject *f_locals; /* Strong reference, may be NULL. Only valid if not on C stack */
    PyFrameObject *frame_obj; /* Strong reference, may be NULL. Only valid if not on C stack */
    // NOTE: This is not necessarily the last instruction started in the given
    // frame. Rather, it is the code unit *prior to* the *next* instruction. For
    // example, it may be an inline CACHE entry, an instruction we just jumped
    // over, or (in the case of a newly-created frame) a totally invalid value:
    _Py_CODEUNIT *prev_instr;
    int stacktop;  /* Offset of TOS from localsplus  */
    /* The return_offset determines where a `RETURN` should go in the caller,
     * relative to `prev_instr`.
     * It is only meaningful to the callee,
     * so it needs to be set in any CALL (to a Python function)
     * or SEND (to a coroutine or generator).
     * If there is no callee, then it is meaningless. */
    uint16_t return_offset;
    char owner;
    /* Locals and stack */
    PyObject *localsplus[1];
};

static void
PyFrame_Copy(struct _PyInterpreterFrame *const src, struct _PyInterpreterFrame *dest, PyObject *const backupFunc) {
    assert(src->previous == NULL);
    const int stacktop = src->stacktop;
    assert(stacktop >= src->f_code->co_nlocalsplus);
    memmove(dest, src, sizeof(PyObject *) * stacktop + sizeof(struct _PyInterpreterFrame));
    for (int off = 0; off < stacktop; ++off) {
        if (dest->localsplus[off] != NULL) {
            dest->localsplus[off] = PyObject_CallOneArg(backupFunc, dest->localsplus[off]);
        }
    }

    if (dest->f_locals != NULL)
        dest->f_locals = PyObject_CallOneArg(backupFunc, dest->f_locals);
    Py_XINCREF(dest->f_code);
    Py_XINCREF(dest->f_funcobj);
}

static PyObject *backup(PyObject *const self, PyObject *const *args, Py_ssize_t nargs) {
    if (nargs != 2 || !PyGen_CheckExact(args[0]) || !PyCallable_Check(args[1])) {
        PyErr_SetString(PyExc_ValueError, "expects (<generator>, <callable>)");
        return NULL;
    }

    PyGenObject *const g = (PyGenObject *) args[0];
    assert(g->gi_weakreflist == NULL);
    assert(g->gi_origin_or_finalizer == NULL);
    assert(g->gi_exc_state.exc_value == NULL);
    assert(g->gi_exc_state.previous_item == NULL);

    struct _PyInterpreterFrame *iframe = (struct _PyInterpreterFrame *) g->gi_iframe;
    assert(iframe->frame_obj == NULL);

    int size = iframe->f_code->co_nlocalsplus + iframe->f_code->co_stacksize;
    PyGenObject *gen = PyObject_GC_NewVar(PyGenObject, &PyGen_Type, size);
    assert(gen != NULL);

    gen->gi_weakreflist = NULL;
    Py_XINCREF(gen->gi_name = g->gi_name);
    Py_XINCREF(gen->gi_qualname = g->gi_qualname);
    gen->gi_exc_state.exc_value = NULL;
    gen->gi_exc_state.previous_item = NULL;
    gen->gi_origin_or_finalizer = NULL;
    gen->gi_hooks_inited = g->gi_hooks_inited;
    gen->gi_closed = g->gi_closed;
    gen->gi_running_async = g->gi_running_async;
    gen->gi_frame_state = g->gi_frame_state;

    PyFrame_Copy(iframe, (struct _PyInterpreterFrame *) gen->gi_iframe, args[1]);

    PyObject_GC_Track(gen);
    return (PyObject *) gen;
}

static PyObject *inflate(PyObject *const self, PyObject *const *args, Py_ssize_t nargs) {
    if (nargs != 2 || !PyGen_CheckExact(args[0]) || !PyCallable_Check(args[1])) {
        PyErr_SetString(PyExc_ValueError, "expects (<generator>, <callable>)");
        return NULL;
    }

    PyGenObject *const g = (PyGenObject *) args[0];
    struct _PyInterpreterFrame *f = (struct _PyInterpreterFrame *) g->gi_iframe;

    const int stacktop = f->stacktop;
    assert(stacktop >= f->f_code->co_nlocalsplus);
    for (int off = 0; off < stacktop; ++off) {
        if (f->localsplus[off] != NULL) {
            f->localsplus[off] = PyObject_CallOneArg(args[1], f->localsplus[off]);
        }
    }
    if (f->f_locals != NULL)
        f->f_locals = PyObject_CallOneArg(args[1], f->f_locals);

    Py_RETURN_NONE;
}

static PyMethodDef MyMethods[] = {
    {"backup",  (PyCFunction) backup,  METH_FASTCALL, "Function that backs up your generator."},
    {"inflate", (PyCFunction) inflate, METH_FASTCALL, "Function that inflates the backup."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef hacks = {
    PyModuleDef_HEAD_INIT,
    "generator_hack",
    "A module that hacks generator internals.",
    -1,
    MyMethods
};

PyMODINIT_FUNC PyInit_generator_hack(void) {
    return PyModule_Create(&hacks);
}
/* Count PyObject allocations (OBJ-domain malloc, calloc, and realloc).

The hooks wrap the allocator already installed in this process and only
increment a counter. They do not allocate.
*/
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

static uint64_t alloc_events = 0;
static int counting = 0;
static int installed = 0;
static PyMemAllocatorEx original;

static void *count_malloc(void *ctx, size_t size) {
    (void)ctx;
    if (counting) {
        alloc_events++;
    }
    return original.malloc(original.ctx, size);
}

static void *count_calloc(void *ctx, size_t nelem, size_t elsize) {
    (void)ctx;
    if (counting) {
        alloc_events++;
    }
    return original.calloc(original.ctx, nelem, elsize);
}

static void *count_realloc(void *ctx, void *ptr, size_t new_size) {
    (void)ctx;
    if (counting) {
        alloc_events++;
    }
    return original.realloc(original.ctx, ptr, new_size);
}

static void count_free(void *ctx, void *ptr) {
    (void)ctx;
    original.free(original.ctx, ptr);
}

static PyObject *py_install(PyObject *self, PyObject *unused) {
    (void)self;
    (void)unused;
    if (!installed) {
        PyMemAllocatorEx hook;
        PyMem_GetAllocator(PYMEM_DOMAIN_OBJ, &original);
        hook.ctx = NULL;
        hook.malloc = count_malloc;
        hook.calloc = count_calloc;
        hook.realloc = count_realloc;
        hook.free = count_free;
        PyMem_SetAllocator(PYMEM_DOMAIN_OBJ, &hook);
        installed = 1;
    }
    Py_RETURN_NONE;
}

static PyObject *py_start(PyObject *self, PyObject *unused) {
    (void)self;
    (void)unused;
    alloc_events = 0;
    counting = 1;
    Py_RETURN_NONE;
}

static PyObject *py_stop(PyObject *self, PyObject *unused) {
    (void)self;
    (void)unused;
    counting = 0;
    Py_RETURN_NONE;
}

static PyObject *py_count(PyObject *self, PyObject *unused) {
    (void)self;
    (void)unused;
    return PyLong_FromUnsignedLongLong(alloc_events);
}

static PyMethodDef methods[] = {
    {"install", py_install, METH_NOARGS, NULL},
    {"start", py_start, METH_NOARGS, NULL},
    {"stop", py_stop, METH_NOARGS, NULL},
    {"count", py_count, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "alloccount",
    NULL,
    -1,
    methods,
};

PyMODINIT_FUNC PyInit_alloccount(void) {
    return PyModule_Create(&module);
}

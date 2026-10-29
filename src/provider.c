// Native COM bridge; CAD parsing runs only in a bounded child process.
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <objbase.h>
#include <objidl.h>
#include <propsys.h>
#include <thumbcache.h>
#include <stddef.h>
#include "worker.h"

static const CLSID CLSID_StepThumbnail = {0xfad54c2d, 0xa5a1, 0x4d8e, {0x91, 0x49, 0x77, 0x98, 0x62, 0xe2, 0xe9, 0x61}};
#ifdef STEP_TEST_ALIAS
static const CLSID CLSID_TestThumbnail = {0xaa69b594, 0xa5d6, 0x4a89, {0x81, 0x45, 0x2a, 0xe8, 0xaf, 0x92, 0x74, 0xcd}};
#endif
static const IID STEP_IID_Thumbnail = {0xe357fccd, 0xa995, 0x4576, {0xb0, 0x1f, 0x23, 0x46, 0x30, 0x15, 0x4e, 0x96}};
static HMODULE module;
static volatile LONG objects;
static volatile LONG locks;
#define MAX_INPUT (64UL * 1024 * 1024)

typedef struct Provider {
    IThumbnailProvider thumbnail;
    IInitializeWithStream initialize;
    LONG references;
    IStream *stream;
    SRWLOCK state_lock;
} Provider;

static HRESULT query(Provider *self, REFIID iid, void **out) {
    if (!out) return E_POINTER;
    *out = NULL;
    if (IsEqualIID(iid, &IID_IUnknown) || IsEqualIID(iid, &STEP_IID_Thumbnail))
        *out = &self->thumbnail;
    else if (IsEqualIID(iid, &IID_IInitializeWithStream))
        *out = &self->initialize;
    else return E_NOINTERFACE;
    InterlockedIncrement(&self->references);
    return S_OK;
}
static ULONG release(Provider *self) {
    LONG count = InterlockedDecrement(&self->references);
    if (!count) {
        if (self->stream) IStream_Release(self->stream);
        HeapFree(GetProcessHeap(), 0, self);
        InterlockedDecrement(&objects);
    }
    return (ULONG)count;
}
static Provider *from_init(IInitializeWithStream *self) {
    return (Provider *)((BYTE *)self - offsetof(Provider, initialize));
}
static HRESULT STDMETHODCALLTYPE thumb_query(IThumbnailProvider *self, REFIID iid, void **out) { return query((Provider *)self, iid, out); }
static ULONG STDMETHODCALLTYPE thumb_add(IThumbnailProvider *self) { return InterlockedIncrement(&((Provider *)self)->references); }
static ULONG STDMETHODCALLTYPE thumb_release(IThumbnailProvider *self) { return release((Provider *)self); }
static HRESULT STDMETHODCALLTYPE init_query(IInitializeWithStream *self, REFIID iid, void **out) { return query(from_init(self), iid, out); }
static ULONG STDMETHODCALLTYPE init_add(IInitializeWithStream *self) { return InterlockedIncrement(&from_init(self)->references); }
static ULONG STDMETHODCALLTYPE init_release(IInitializeWithStream *self) { return release(from_init(self)); }
static HRESULT STDMETHODCALLTYPE initialize(IInitializeWithStream *iface, IStream *stream, DWORD mode) {
    (void)mode;
    Provider *self = from_init(iface);
    if (!stream) return E_INVALIDARG;
    if (!TryAcquireSRWLockExclusive(&self->state_lock)) return HRESULT_FROM_WIN32(ERROR_BUSY);
    if (self->stream) {
        ReleaseSRWLockExclusive(&self->state_lock);
        return HRESULT_FROM_WIN32(ERROR_ALREADY_INITIALIZED);
    }
    self->stream = stream;
    IStream_AddRef(stream);
    ReleaseSRWLockExclusive(&self->state_lock);
    return S_OK;
}
static HRESULT thumbnail_locked(IThumbnailProvider *iface, UINT size, HBITMAP *bitmap, WTS_ALPHATYPE *alpha) {
    if (!bitmap || !alpha) return E_POINTER;
    *bitmap = NULL;
    *alpha = WTSAT_UNKNOWN;
    Provider *self = (Provider *)iface;
    if (!self->stream) return E_UNEXPECTED;
    if (!size || size > 1024) return E_INVALIDARG;
    LARGE_INTEGER zero = {0};
    HRESULT result = IStream_Seek(self->stream, zero, STREAM_SEEK_SET, NULL);
    if (FAILED(result)) return result;
    STATSTG stat = {0};
    if (SUCCEEDED(IStream_Stat(self->stream, &stat, STATFLAG_NONAME)) && stat.cbSize.QuadPart > MAX_INPUT)
        return HRESULT_FROM_WIN32(ERROR_FILE_TOO_LARGE);
    DWORD capacity = 65536, length = 0;
    BYTE *data = HeapAlloc(GetProcessHeap(), 0, capacity);
    if (!data) return E_OUTOFMEMORY;
    for (;;) {
        if (length == capacity) {
            DWORD next = capacity > MAX_INPUT / 2 ? MAX_INPUT + 1 : capacity * 2;
            BYTE *grown = HeapReAlloc(GetProcessHeap(), 0, data, next);
            if (!grown) { result = E_OUTOFMEMORY; break; }
            data = grown;
            capacity = next;
        }
        ULONG read = 0;
        result = IStream_Read(self->stream, data + length, capacity - length, &read);
        if (FAILED(result)) break;
        length += read;
        if (length > MAX_INPUT) { result = HRESULT_FROM_WIN32(ERROR_FILE_TOO_LARGE); break; }
        if (!read) {
            result = length ? StepWorkerRender(module, data, length, size, bitmap) : E_INVALIDARG;
            if (SUCCEEDED(result)) *alpha = WTSAT_ARGB;
            break;
        }
    }
    HeapFree(GetProcessHeap(), 0, data);
    return result;
}
static HRESULT STDMETHODCALLTYPE thumbnail(IThumbnailProvider *iface, UINT size, HBITMAP *bitmap, WTS_ALPHATYPE *alpha) {
    if (!bitmap || !alpha) return E_POINTER;
    *bitmap = NULL;
    *alpha = WTSAT_UNKNOWN;
    Provider *self = (Provider *)iface;
    if (!TryAcquireSRWLockExclusive(&self->state_lock)) return HRESULT_FROM_WIN32(ERROR_BUSY);
    HRESULT result = thumbnail_locked(iface, size, bitmap, alpha);
    ReleaseSRWLockExclusive(&self->state_lock);
    return result;
}
static IThumbnailProviderVtbl thumbnail_vtable = {thumb_query, thumb_add, thumb_release, thumbnail};
static IInitializeWithStreamVtbl initialize_vtable = {init_query, init_add, init_release, initialize};

typedef struct Factory { IClassFactory iface; LONG references; } Factory;
static HRESULT STDMETHODCALLTYPE factory_query(IClassFactory *iface, REFIID iid, void **out) {
    if (!out) return E_POINTER;
    *out = NULL;
    if (!IsEqualIID(iid, &IID_IUnknown) && !IsEqualIID(iid, &IID_IClassFactory)) return E_NOINTERFACE;
    *out = iface;
    InterlockedIncrement(&((Factory *)iface)->references);
    return S_OK;
}
static ULONG STDMETHODCALLTYPE factory_add(IClassFactory *self) { return InterlockedIncrement(&((Factory *)self)->references); }
static ULONG STDMETHODCALLTYPE factory_release(IClassFactory *self) {
    LONG count = InterlockedDecrement(&((Factory *)self)->references);
    if (!count) { HeapFree(GetProcessHeap(), 0, self); InterlockedDecrement(&objects); }
    return (ULONG)count;
}
static HRESULT STDMETHODCALLTYPE factory_create(IClassFactory *factory, IUnknown *outer, REFIID iid, void **out) {
    (void)factory;
    if (!out) return E_POINTER;
    *out = NULL;
    if (outer) return CLASS_E_NOAGGREGATION;
    Provider *self = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*self));
    if (!self) return E_OUTOFMEMORY;
    self->thumbnail.lpVtbl = &thumbnail_vtable;
    self->initialize.lpVtbl = &initialize_vtable;
    self->references = 1;
    InitializeSRWLock(&self->state_lock);
    InterlockedIncrement(&objects);
    HRESULT result = query(self, iid, out);
    release(self);
    return result;
}
static HRESULT STDMETHODCALLTYPE factory_lock(IClassFactory *self, BOOL lock) {
    (void)self;
    if (lock) InterlockedIncrement(&locks); else InterlockedDecrement(&locks);
    return S_OK;
}
static IClassFactoryVtbl factory_vtable = {factory_query, factory_add, factory_release, factory_create, factory_lock};
HRESULT WINAPI DllGetClassObject(REFCLSID clsid, REFIID iid, void **out) {
    if (!out) return E_POINTER;
    *out = NULL;
    BOOL supported = IsEqualCLSID(clsid, &CLSID_StepThumbnail);
#ifdef STEP_TEST_ALIAS
    supported = supported || IsEqualCLSID(clsid, &CLSID_TestThumbnail);
#endif
    if (!supported) return CLASS_E_CLASSNOTAVAILABLE;
    Factory *self = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*self));
    if (!self) return E_OUTOFMEMORY;
    self->iface.lpVtbl = &factory_vtable;
    self->references = 1;
    InterlockedIncrement(&objects);
    HRESULT result = factory_query(&self->iface, iid, out);
    factory_release(&self->iface);
    return result;
}
HRESULT WINAPI DllCanUnloadNow(void) { return objects == 0 && locks == 0 && StepWorkerCanUnload() ? S_OK : S_FALSE; }
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, void *reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) { module = instance; DisableThreadLibraryCalls(instance); }
    if (reason == DLL_PROCESS_DETACH) StepWorkerDetach();
    return TRUE;
}

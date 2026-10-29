// Two isolated, bounded workers per COM host. No CAD/runtime code in the host.
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include "worker.h"
#include <stdio.h>
#include <string.h>

#ifndef STEP_TIMEOUT_MS
#define STEP_TIMEOUT_MS 20000
#endif
#ifndef STEP_IDLE_MS
#define STEP_IDLE_MS 30000
#endif
#ifndef STEP_MAX_REQUESTS
#define STEP_MAX_REQUESTS 32
#endif
#define STEP_WORKERS 2

typedef struct Worker {
    HANDLE input, output, process, job;
    ULONGLONG last_used;
    DWORD requests;
} Worker;
typedef struct WorkerSlot {
    SRWLOCK lock;
    Worker state;
} WorkerSlot;
static WorkerSlot workers[STEP_WORKERS]; // SRWLOCK_INIT is all-zero on Windows.

typedef struct Writer {
    HANDLE pipe;
    const BYTE *data;
    DWORD length, size;
    BOOL success;
} Writer;

static void close_worker(Worker *worker) {
    if (worker->job) CloseHandle(worker->job); // KILL_ON_JOB_CLOSE, including a hung worker
    if (worker->process) {
        if (WaitForSingleObject(worker->process, 0) != WAIT_OBJECT_0) TerminateProcess(worker->process, 1);
        WaitForSingleObject(worker->process, INFINITE);
        CloseHandle(worker->process);
    }
    if (worker->input) CloseHandle(worker->input);
    if (worker->output) CloseHandle(worker->output);
    memset(worker, 0, sizeof(*worker));
}

// DllMain must not wait for another process or acquire a lock under loader lock.
void StepWorkerDetach(void) {
    for (unsigned i = 0; i < STEP_WORKERS; ++i) {
        Worker *worker = &workers[i].state;
        if (worker->job) CloseHandle(worker->job);
        if (worker->process) CloseHandle(worker->process);
        if (worker->input) CloseHandle(worker->input);
        if (worker->output) CloseHandle(worker->output);
        memset(worker, 0, sizeof(*worker));
    }
}

BOOL StepWorkerCanUnload(void) {
    BOOL ready = TRUE;
    for (unsigned i = 0; i < STEP_WORKERS; ++i) {
        WorkerSlot *slot = &workers[i];
        if (!TryAcquireSRWLockExclusive(&slot->lock)) { ready = FALSE; continue; }
        Worker *worker = &slot->state;
        if (worker->process && (WaitForSingleObject(worker->process, 0) == WAIT_OBJECT_0 ||
            GetTickCount64() - worker->last_used >= STEP_IDLE_MS)) close_worker(worker);
        if (worker->process) ready = FALSE;
        ReleaseSRWLockExclusive(&slot->lock);
    }
    return ready;
}

static HRESULT start_worker(HMODULE module, Worker *worker) {
    HANDLE input_read = NULL, output_write = NULL, errors = INVALID_HANDLE_VALUE;
    PROCESS_INFORMATION process = {0};
    SECURITY_ATTRIBUTES security = {sizeof(security), NULL, TRUE};
    HRESULT result = E_FAIL;
    wchar_t folder[32768], python[32768], command[65536];
    DWORD path_length = GetModuleFileNameW(module, folder, ARRAYSIZE(folder));
    if (!path_length || path_length >= ARRAYSIZE(folder)) return E_FAIL;
    wchar_t *slash = wcsrchr(folder, L'\\');
    if (!slash) return E_FAIL;
    *slash = 0;
    if (swprintf(python, ARRAYSIZE(python), L"%ls\\runtime\\python.exe", folder) < 0 ||
        swprintf(command, ARRAYSIZE(command),
            L"\"%ls\" -I -B \"%ls\\render_step.py\" --server --idle-ms %u --max-requests %u",
            python, folder, (unsigned)STEP_IDLE_MS, (unsigned)STEP_MAX_REQUESTS) < 0) return E_FAIL;
    if (!CreatePipe(&input_read, &worker->input, &security, 65536) ||
        !SetHandleInformation(worker->input, HANDLE_FLAG_INHERIT, 0) ||
        !CreatePipe(&worker->output, &output_write, &security, 65536) ||
        !SetHandleInformation(worker->output, HANDLE_FLAG_INHERIT, 0)) goto cleanup;
    errors = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                        &security, OPEN_EXISTING, 0, NULL);
    if (errors == INVALID_HANDLE_VALUE) goto cleanup;

    SIZE_T attribute_size = 0;
    InitializeProcThreadAttributeList(NULL, 1, 0, &attribute_size);
    STARTUPINFOEXW startup = {0};
    startup.StartupInfo.cb = sizeof(startup);
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = input_read;
    startup.StartupInfo.hStdOutput = output_write;
    startup.StartupInfo.hStdError = errors;
    startup.lpAttributeList = HeapAlloc(GetProcessHeap(), 0, attribute_size);
    if (!startup.lpAttributeList) { result = E_OUTOFMEMORY; goto cleanup; }
    if (!InitializeProcThreadAttributeList(startup.lpAttributeList, 1, 0, &attribute_size)) {
        HeapFree(GetProcessHeap(), 0, startup.lpAttributeList);
        goto cleanup;
    }
    HANDLE inherited[] = {input_read, output_write, errors};
    BOOL prepared = UpdateProcThreadAttribute(startup.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                                             inherited, sizeof(inherited), NULL, NULL);
    BOOL started = prepared && CreateProcessW(python, command, NULL, NULL, TRUE,
        CREATE_NO_WINDOW | CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT, NULL, folder,
        &startup.StartupInfo, &process);
    DeleteProcThreadAttributeList(startup.lpAttributeList);
    HeapFree(GetProcessHeap(), 0, startup.lpAttributeList);
    if (!started) goto cleanup;
    worker->process = process.hProcess;
    worker->job = CreateJobObjectW(NULL, NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {0};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
        JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_ACTIVE_PROCESS;
    limits.BasicLimitInformation.ActiveProcessLimit = 1;
    limits.ProcessMemoryLimit = (SIZE_T)1024 * 1024 * 1024;
    if (!worker->job || !SetInformationJobObject(worker->job, JobObjectExtendedLimitInformation, &limits, sizeof(limits)) ||
        !AssignProcessToJobObject(worker->job, worker->process) || ResumeThread(process.hThread) == (DWORD)-1) goto cleanup;
    worker->last_used = GetTickCount64();
    result = S_OK;
cleanup:
    if (process.hThread) CloseHandle(process.hThread);
    if (input_read) CloseHandle(input_read);
    if (output_write) CloseHandle(output_write);
    if (errors != INVALID_HANDLE_VALUE) CloseHandle(errors);
    if (FAILED(result)) close_worker(worker);
    return result;
}

static BOOL write_all(HANDLE pipe, const BYTE *data, DWORD length) {
    DWORD offset = 0;
    while (offset < length) {
        DWORD written = 0;
        DWORD amount = length - offset;
        if (amount > 65536) amount = 65536;
        if (!WriteFile(pipe, data + offset, amount, &written, NULL) || !written) return FALSE;
        offset += written;
    }
    return TRUE;
}

static DWORD WINAPI write_request(void *context) {
    Writer *writer = context;
    DWORD header[] = {0x32514552, writer->size, writer->length}; // REQ2, width, input bytes
    writer->success = write_all(writer->pipe, (const BYTE *)header, sizeof(header)) &&
                      write_all(writer->pipe, writer->data, writer->length);
    return 0;
}

static HRESULT read_exact(Worker *worker, BYTE *output, DWORD length, ULONGLONG deadline) {
    DWORD offset = 0;
    while (offset < length) {
        if (GetTickCount64() >= deadline) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
        DWORD available = 0;
        if (!PeekNamedPipe(worker->output, NULL, 0, NULL, &available, NULL))
            return HRESULT_FROM_WIN32(GetLastError());
        if (!available) { Sleep(1); continue; }
        DWORD amount = length - offset, read = 0;
        if (available < amount) amount = available;
        if (!ReadFile(worker->output, output + offset, amount, &read, NULL) || !read)
            return HRESULT_FROM_WIN32(ERROR_BROKEN_PIPE);
        offset += read;
    }
    return S_OK;
}

HRESULT StepWorkerRender(HMODULE module, const BYTE *data, DWORD length, UINT size, HBITMAP *bitmap) {
    ULONGLONG deadline = GetTickCount64() + STEP_TIMEOUT_MS;
    WorkerSlot *slot = NULL;
    // Prefer an existing idle process; create a second process only when needed.
    while (!slot && GetTickCount64() < deadline) {
        for (unsigned pass = 0; pass < 2 && !slot; ++pass) {
            for (unsigned i = 0; i < STEP_WORKERS; ++i) {
                WorkerSlot *candidate = &workers[i];
                if (!TryAcquireSRWLockExclusive(&candidate->lock)) continue;
                if (pass == 0 && (!candidate->state.process ||
                    WaitForSingleObject(candidate->state.process, 0) == WAIT_OBJECT_0 ||
                    candidate->state.requests >= STEP_MAX_REQUESTS)) {
                    ReleaseSRWLockExclusive(&candidate->lock);
                    continue;
                }
                slot = candidate;
                break;
            }
        }
        if (!slot) Sleep(1);
    }
    if (!slot) return HRESULT_FROM_WIN32(ERROR_TIMEOUT);
    Worker *worker = &slot->state;
    HRESULT result = E_FAIL;
    BOOL healthy = FALSE;
    HANDLE thread = NULL;
    Writer writer = {0};
    BYTE *pixels = NULL;
    DWORD idle_margin = STEP_IDLE_MS / 4 < 1000 ? STEP_IDLE_MS / 4 : 1000;
    if (worker->process && (WaitForSingleObject(worker->process, 0) == WAIT_OBJECT_0 ||
        worker->requests >= STEP_MAX_REQUESTS ||
        GetTickCount64() - worker->last_used >= STEP_IDLE_MS - idle_margin)) close_worker(worker);
    if (!worker->process) {
        result = start_worker(module, worker);
        if (FAILED(result)) goto cleanup;
    }
    writer.pipe = worker->input;
    writer.data = data;
    writer.length = length;
    writer.size = size;
    thread = CreateThread(NULL, 0, write_request, &writer, 0, NULL);
    if (!thread) { result = E_OUTOFMEMORY; goto cleanup; }
    DWORD header[4]; // STP2, status (0=success, 1=model error), width, height
    result = read_exact(worker, (BYTE *)header, sizeof(header), deadline);
    if (FAILED(result)) goto cleanup;
    if (header[0] != 0x32505453 || header[1] > 1 ||
        (header[1] == 0 && (header[2] != size || header[3] != size)) ||
        (header[1] == 1 && (header[2] || header[3]))) { result = E_FAIL; goto cleanup; }
    if (header[1] == 0) {
        DWORD bytes = size * size * 4;
        pixels = HeapAlloc(GetProcessHeap(), 0, bytes);
        if (!pixels) { result = E_OUTOFMEMORY; goto cleanup; }
        result = read_exact(worker, pixels, bytes, deadline);
        if (FAILED(result)) goto cleanup;
    }
    ULONGLONG now = GetTickCount64();
    if (WaitForSingleObject(thread, now < deadline ? (DWORD)(deadline - now) : 0) != WAIT_OBJECT_0 ||
        !writer.success) { result = E_FAIL; goto cleanup; }
    DWORD available = 0;
    if (PeekNamedPipe(worker->output, NULL, 0, NULL, &available, NULL) && available) { result = E_FAIL; goto cleanup; }
    healthy = TRUE;
    worker->last_used = GetTickCount64();
    worker->requests++;
    if (header[1]) { result = E_FAIL; goto cleanup; }
    BITMAPINFO info = {0};
    info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth = (LONG)size;
    info.bmiHeader.biHeight = -(LONG)size;
    info.bmiHeader.biPlanes = 1;
    info.bmiHeader.biBitCount = 32;
    info.bmiHeader.biCompression = BI_RGB;
    void *target = NULL;
    *bitmap = CreateDIBSection(NULL, &info, DIB_RGB_COLORS, &target, NULL, 0);
    if (!*bitmap) { result = E_OUTOFMEMORY; goto cleanup; }
    memcpy(target, pixels, size * size * 4);
    result = S_OK;
cleanup:
    // Keep the parent pipe handle valid until the writer has actually stopped.
    if (!healthy && worker->process) TerminateProcess(worker->process, 1);
    if (thread) {
        CancelSynchronousIo(thread);
        WaitForSingleObject(thread, INFINITE);
        CloseHandle(thread);
    }
    if (!healthy) close_worker(worker);
    if (pixels) HeapFree(GetProcessHeap(), 0, pixels);
    ReleaseSRWLockExclusive(&slot->lock);
    return result;
}

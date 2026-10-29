// Deterministic process failure/reuse tests; not distributed with the product.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static BOOL transfer(HANDLE pipe, void *buffer, DWORD length, BOOL write) {
    BYTE *bytes = buffer;
    DWORD offset = 0;
    while (offset < length) {
        DWORD count = 0;
        BOOL ok = write ? WriteFile(pipe, bytes + offset, length - offset, &count, NULL) :
                          ReadFile(pipe, bytes + offset, length - offset, &count, NULL);
        if (!ok || !count) return FALSE;
        offset += count;
    }
    return TRUE;
}

int main(void) {
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {0};
    if (!QueryInformationJobObject(NULL, JobObjectExtendedLimitInformation, &limits, sizeof(limits), NULL) ||
        limits.ProcessMemoryLimit != (SIZE_T)1024 * 1024 * 1024 ||
        limits.BasicLimitInformation.ActiveProcessLimit != 1) return 2;
    HANDLE input = GetStdHandle(STD_INPUT_HANDLE), output = GetStdHandle(STD_OUTPUT_HANDLE);
    for (;;) {
        DWORD request[3];
        if (!transfer(input, request, sizeof(request), FALSE)) return 0;
        if (request[0] != 0x32514552 || !request[2] || request[2] > 67108864) return 1;
        BYTE *data = malloc(request[2]);
        if (!data || !transfer(input, data, 1, FALSE)) return 1;
        char action = (char)data[0];
        if (action == 'H') Sleep(10000); // Stop reading while the parent's writer is blocked.
        if (!transfer(input, data + 1, request[2] - 1, FALSE)) return 1;
        free(data);
        if (action == 'X') return 1;
        if (action == 'S') Sleep(10000);
        if (action == 'W') Sleep(500);
        if (action == 'L') Sleep(1200);
        DWORD response[] = {0x32505453, 0, request[1], request[1]};
        if (action == 'B') response[0] = 0;
        if (action == 'E') { response[1] = 1; response[2] = response[3] = 0; }
        if (!transfer(output, response, sizeof(response), TRUE)) return 0;
        if (action == 'E') continue;
        DWORD length = request[1] * request[1] * 4;
        BYTE *pixels = malloc(length);
        if (!pixels) return 1;
        memset(pixels, 255, length);
        memcpy(pixels, &(DWORD){GetCurrentProcessId()}, 4);
        BOOL sent = transfer(output, pixels, length, TRUE);
        free(pixels);
        if (!sent) return 0;
    }
}

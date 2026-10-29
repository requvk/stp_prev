#pragma once
#include <windows.h>

HRESULT StepWorkerRender(HMODULE module, const BYTE *data, DWORD length, UINT size, HBITMAP *bitmap);
BOOL StepWorkerCanUnload(void);
void StepWorkerDetach(void);

/* Keep the Windows headers in an isolated translation unit.  UQM's original
 * public types include names such as DWORD, POINT, RECT, and CONTEXT, which
 * intentionally predate and conflict with the Win32 declarations. */
#ifdef WIN32

#include <windows.h>

#include "clipboard_win.h"

int
TFB_Win32_CopyRGBAToClipboard (const unsigned char *pixels,
		int width, int height, int pitch)
{
	BITMAPINFOHEADER *header;
	HGLOBAL memory;
	DWORD image_size;
	DWORD allocation_size;
	unsigned char *destination;
	const unsigned char *source_row;
	unsigned char *destination_row;
	int x;
	int y;

	image_size = (DWORD) width * (DWORD) height * 4;
	allocation_size = sizeof (*header) + image_size;
	memory = GlobalAlloc (GMEM_MOVEABLE, allocation_size);
	if (memory == NULL)
		return 0;

	header = (BITMAPINFOHEADER *) GlobalLock (memory);
	if (header == NULL)
	{
		GlobalFree (memory);
		return 0;
	}
	ZeroMemory (header, sizeof (*header));
	header->biSize = sizeof (*header);
	header->biWidth = width;
	header->biHeight = height;
	header->biPlanes = 1;
	header->biBitCount = 32;
	header->biCompression = BI_RGB;
	header->biSizeImage = image_size;
	destination = (unsigned char *) (header + 1);
	for (y = 0; y < height; ++y)
	{
		/* A positive-height DIB is bottom-up. */
		source_row = pixels + (height - y - 1) * pitch;
		destination_row = destination + y * width * 4;
		for (x = 0; x < width; ++x)
		{
			destination_row[x * 4 + 0] = source_row[x * 4 + 2];
			destination_row[x * 4 + 1] = source_row[x * 4 + 1];
			destination_row[x * 4 + 2] = source_row[x * 4 + 0];
			destination_row[x * 4 + 3] = 0;
		}
	}
	GlobalUnlock (memory);

	if (!OpenClipboard (NULL))
	{
		GlobalFree (memory);
		return 0;
	}
	EmptyClipboard ();
	if (SetClipboardData (CF_DIB, memory) == NULL)
	{
		CloseClipboard ();
		GlobalFree (memory);
		return 0;
	}
	CloseClipboard ();
	/* Windows owns memory after SetClipboardData succeeds. */
	return 1;
}

#endif

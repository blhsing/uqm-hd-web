#ifndef UQM_SDL_COMPAT_H
#define UQM_SDL_COMPAT_H

#include "port.h"
#include SDL_INCLUDE(SDL.h)

#ifdef __EMSCRIPTEN__
/* SDL 2 removed these SDL 1.2 surface flags.  The old engine still passes
 * them as boolean arguments to SDL_SetColorKey, so retain harmless values
 * while the wrappers below translate the operations that changed API. */
#ifndef SDL_SRCCOLORKEY
#define SDL_SRCCOLORKEY 0x00001000
#endif
#ifndef SDL_SRCALPHA
#define SDL_SRCALPHA 0x00010000
#endif
#endif

static inline int
TFB_SetSurfaceAlpha (SDL_Surface *surface, int enabled, Uint8 alpha)
{
#ifdef __EMSCRIPTEN__
	if (SDL_SetSurfaceAlphaMod (surface, alpha) != 0)
		return -1;
	return SDL_SetSurfaceBlendMode (surface,
			enabled ? SDL_BLENDMODE_BLEND : SDL_BLENDMODE_NONE);
#else
	return SDL_SetAlpha (surface, enabled ? SDL_SRCALPHA : 0, alpha);
#endif
}

static inline int
TFB_SetPaletteColors (SDL_Surface *surface, SDL_Color *colors,
		int firstColor, int colorCount)
{
#ifdef __EMSCRIPTEN__
	if (!surface->format->palette)
		return 0;
	return SDL_SetPaletteColors (surface->format->palette, colors,
			firstColor, colorCount) == 0;
#else
	return SDL_SetColors (surface, colors, firstColor, colorCount);
#endif
}

static inline int
TFB_SurfaceGetColorKey (SDL_Surface *surface, Uint32 *colorKey)
{
#ifdef __EMSCRIPTEN__
	return SDL_GetColorKey (surface, colorKey) == 0;
#else
	if (!(surface->flags & SDL_SRCCOLORKEY))
		return 0;
	*colorKey = surface->format->colorkey;
	return 1;
#endif
}

static inline int
TFB_SurfaceHasAlphaMod (SDL_Surface *surface)
{
#ifdef __EMSCRIPTEN__
	Uint8 alpha;
	return SDL_GetSurfaceAlphaMod (surface, &alpha) == 0
			&& alpha != SDL_ALPHA_OPAQUE;
#else
	return (surface->flags & SDL_SRCALPHA) != 0;
#endif
}

static inline Uint32
TFB_SurfaceConversionFlags (SDL_Surface *surface)
{
#ifdef __EMSCRIPTEN__
	(void) surface;
	return 0;
#else
	return surface->flags;
#endif
}

#endif

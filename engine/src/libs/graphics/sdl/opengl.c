//Copyright Paul Reiche, Fred Ford. 1992-2002

/*
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
 */

// JMS_GFX 2012: Merged the resolution Factor stuff from P6014.

#ifdef HAVE_OPENGL

#include <time.h>

#include "libs/graphics/sdl/opengl.h"
#include "libs/graphics/bbox.h"
#include "scalers.h"
#include "options.h"
#include "libs/file.h"
#include "libs/log.h"
#ifdef WIN32
#include "clipboard_win.h"
#endif

typedef struct _gl_screeninfo {
	SDL_Surface *scaled;
	GLuint texture;
	BOOLEAN dirty, active;
	SDL_Rect updated;
} TFB_GL_SCREENINFO;

static TFB_GL_SCREENINFO GL_Screens[TFB_GFX_NUMSCREENS];

static int ScreenFilterMode;
static int ScreenTextureWidth;
static int ScreenTextureHeight;

static TFB_ScaleFunc scaler = NULL;
static BOOLEAN first_init = TRUE;
static volatile BOOLEAN ScreenshotRequested = FALSE;

#if SDL_BYTEORDER == SDL_BIG_ENDIAN
#define R_MASK 0xff000000
#define G_MASK 0x00ff0000
#define B_MASK 0x0000ff00
#define A_MASK 0x000000ff
#else
#define R_MASK 0x000000ff
#define G_MASK 0x0000ff00
#define B_MASK 0x00ff0000
#define A_MASK 0xff000000
#endif

static void TFB_GL_Preprocess (int force_full_redraw, int transition_amount, int fade_amount);
static void TFB_GL_Postprocess (void);
static void TFB_GL_Scaled_ScreenLayer (SCREEN screen, Uint8 a, SDL_Rect *rect);
static void TFB_GL_Unscaled_ScreenLayer (SCREEN screen, Uint8 a, SDL_Rect *rect);
static void TFB_GL_Unscaled_ScreenLayer_2x (SCREEN screen, Uint8 a, SDL_Rect *rect);
static void TFB_GL_Unscaled_ScreenLayer_4x (SCREEN screen, Uint8 a, SDL_Rect *rect);
static void TFB_GL_ColorLayer (Uint8 r, Uint8 g, Uint8 b, Uint8 a, SDL_Rect *rect);

void
TFB_GL_RequestScreenshot (void)
{
	ScreenshotRequested = TRUE;
}

static TFB_GRAPHICS_BACKEND opengl_scaled_backend = {
	TFB_GL_Preprocess,
	TFB_GL_Postprocess,
	TFB_GL_Scaled_ScreenLayer,
	TFB_GL_ColorLayer };

static TFB_GRAPHICS_BACKEND opengl_unscaled_backend = {
	TFB_GL_Preprocess,
	TFB_GL_Postprocess,
	TFB_GL_Unscaled_ScreenLayer,
	TFB_GL_ColorLayer };

static TFB_GRAPHICS_BACKEND opengl_unscaled_backend_2x = {
	TFB_GL_Preprocess,
	TFB_GL_Postprocess,
	TFB_GL_Unscaled_ScreenLayer_2x,
	TFB_GL_ColorLayer };

static TFB_GRAPHICS_BACKEND opengl_unscaled_backend_4x = {
	TFB_GL_Preprocess,
	TFB_GL_Postprocess,
	TFB_GL_Unscaled_ScreenLayer_4x,
	TFB_GL_ColorLayer };


static SDL_Surface *
Create_Screen (SDL_Surface *template, int w, int h)
{
	SDL_Surface *newsurf = SDL_CreateRGBSurface(SDL_SWSURFACE, w, h,
			template->format->BitsPerPixel,
			template->format->Rmask, template->format->Gmask,
			template->format->Bmask, 0);
	if (newsurf == 0) {
		log_add (log_Error, "Couldn't create screen buffers: %s",
				SDL_GetError());
	}
	return newsurf;
}

static int
ReInit_Screen (SDL_Surface **screen, SDL_Surface *template, int w, int h)
{
	if (*screen)
		SDL_FreeSurface (*screen);
	*screen = Create_Screen (template, w, h);
	
	return *screen == 0 ? -1 : 0;
}

static int
AttemptColorDepth (int flags, int width, int height, int bpp, unsigned int resolutionFactor, BOOLEAN forceAspectRatio)  // JMS_GFX: Added resolutionFactor
{
	int videomode_flags;
	ScreenColorDepth = bpp;
	
	switch (bpp) {
		case 15:
			SDL_GL_SetAttribute (SDL_GL_RED_SIZE, 5);
			SDL_GL_SetAttribute (SDL_GL_GREEN_SIZE, 5);
			SDL_GL_SetAttribute (SDL_GL_BLUE_SIZE, 5);
			break;

		case 16:
			SDL_GL_SetAttribute (SDL_GL_RED_SIZE, 5);
			SDL_GL_SetAttribute (SDL_GL_GREEN_SIZE, 6);
			SDL_GL_SetAttribute (SDL_GL_BLUE_SIZE, 5);
			break;

		case 24:
			SDL_GL_SetAttribute (SDL_GL_RED_SIZE, 8);
			SDL_GL_SetAttribute (SDL_GL_GREEN_SIZE, 8);
			SDL_GL_SetAttribute (SDL_GL_BLUE_SIZE, 8);
			break;

		case 32:
			SDL_GL_SetAttribute (SDL_GL_RED_SIZE, 8);
			SDL_GL_SetAttribute (SDL_GL_GREEN_SIZE, 8);
			SDL_GL_SetAttribute (SDL_GL_BLUE_SIZE, 8);
			break;
		default:
			break;
	}

	SDL_GL_SetAttribute (SDL_GL_DEPTH_SIZE, 0);
	SDL_GL_SetAttribute (SDL_GL_DOUBLEBUFFER, 1);

	videomode_flags = SDL_OPENGL;
	if (flags & TFB_GFXFLAGS_FULLSCREEN)
		videomode_flags |= SDL_FULLSCREEN;
	videomode_flags |= SDL_ANYFORMAT;

	if (resolutionFactor > 0 && flags & TFB_GFXFLAGS_FULLSCREEN)
	{
		height = fs_height;
		width  = fs_width;
			
		log_add (log_Debug,"X:%d y:%d", width, height);
	}
	
	ScreenWidthActual = width;
	ScreenHeightActual = height;

	SDL_Video = SDL_SetVideoMode (ScreenWidthActual, ScreenHeightActual, bpp, videomode_flags);
	
	if (SDL_Video == NULL)
	{
		log_add (log_Error, "Couldn't set OpenGL %ix%ix%i video mode: %s",
				ScreenWidthActual, ScreenHeightActual, bpp,
				SDL_GetError ());
		
		if (flags & TFB_GFXFLAGS_FULLSCREEN)
		{
			videomode_flags &= ~SDL_FULLSCREEN;
			log_add (log_Error, "Falling back to windowed mode!!");
			SDL_Video = SDL_SetVideoMode (ScreenWidthActual, ScreenHeightActual, bpp, videomode_flags);
			
			if (SDL_Video != NULL)
				goto successful_change;
		}
		
		return -1;
	}
	else
	{
	successful_change:
		log_add (log_Info, "Set the resolution to: %ix%ix%i"
				" (surface reports %ix%ix%i) (res_cat %u)",
				width, height, bpp,			 
				SDL_GetVideoSurface()->w, SDL_GetVideoSurface()->h,
				SDL_GetVideoSurface()->format->BitsPerPixel, resolutionFactor);

		log_add (log_Info, "OpenGL renderer: %s version: %s",
				glGetString (GL_RENDERER), glGetString (GL_VERSION));
		
		// JMS: Now, this makes the game center horizontally
		// between the black bars on the sides.
		ScreenWidthActual = SDL_GetVideoSurface()->w;
		
	}
	return 0;
}

int
TFB_GL_ConfigureVideo (int driver, int flags, int width, int height, int togglefullscreen, unsigned int resolutionFactor, BOOLEAN forceAspectRatio)  // JMS_GFX: Added resolutionFactor
{
	int i, texture_width, texture_height;
	GraphicsDriver = driver;

	if (AttemptColorDepth (flags, width, height, 32, resolutionFactor, forceAspectRatio) &&
			AttemptColorDepth (flags, width, height, 24, resolutionFactor, forceAspectRatio) &&
			AttemptColorDepth (flags, width, height, 16, resolutionFactor, forceAspectRatio))
	{
		log_add (log_Error, "Couldn't set any OpenGL %ix%i video mode!",
			 width, height);
		return -1;
	}

	if (!togglefullscreen)
	{
		if (format_conv_surf)
			SDL_FreeSurface (format_conv_surf);
		format_conv_surf = SDL_CreateRGBSurface (SDL_SWSURFACE, 0, 0, 32,
			R_MASK, G_MASK, B_MASK, A_MASK);
		if (format_conv_surf == NULL)
		{
			log_add (log_Error, "Couldn't create format_conv_surf: %s",
					SDL_GetError());
			return -1;
		}

		for (i = 0; i < TFB_GFX_NUMSCREENS; i++)
		{
			if (0 != ReInit_Screen (&SDL_Screens[i], format_conv_surf,
					ScreenWidth, ScreenHeight))
				return -1;
		}

		SDL_Screen = SDL_Screens[0];
		TransitionScreen = SDL_Screens[2];

		if (first_init)
		{
			for (i = 0; i < TFB_GFX_NUMSCREENS; i++)
			{
				GL_Screens[i].scaled = NULL;
				GL_Screens[i].dirty = TRUE;
				GL_Screens[i].active = TRUE;
			}
			GL_Screens[1].active = FALSE;
			first_init = FALSE;
		}
	}

	if (GfxFlags & TFB_GFXFLAGS_SCALE_SOFT_ONLY)
	{
		if (!togglefullscreen)
		{
			for (i = 0; i < TFB_GFX_NUMSCREENS; i++)
			{
				if (!GL_Screens[i].active)
					continue;
				if (0 != ReInit_Screen (&GL_Screens[i].scaled, format_conv_surf,
						ScreenWidth * 2, ScreenHeight * 2))
				return -1;
			}
			scaler = Scale_PrepPlatform (flags, SDL_Screen->format);
		}

		texture_width = 1024;
		texture_height = 512;

		graphics_backend = &opengl_scaled_backend;
	}
	else
	{
		if (resolutionFactor == 0)
		{
			texture_width = 512;
			texture_height = 256;
			graphics_backend = &opengl_unscaled_backend;
		}
		else if (resolutionFactor == 1)
		{
			texture_width = 1024;
			texture_height = 512;
			graphics_backend = &opengl_unscaled_backend_2x;
		}
		else
		{
			/* The 4x and native-supersampled tiers both use the direct
			 * upload backend.  Their backing textures grow with the logical
			 * canvas: 2048x1024 at 4x and 4096x2048 at native 1080p. */
			texture_width = 512 << resolutionFactor;
			texture_height = 256 << resolutionFactor;
			graphics_backend = &opengl_unscaled_backend_4x;
		}

		scaler = NULL;
	}


	if (GfxFlags & TFB_GFXFLAGS_SCALE_ANY)
		ScreenFilterMode = GL_LINEAR;
	else
		ScreenFilterMode = GL_NEAREST;
	ScreenTextureWidth = texture_width;
	ScreenTextureHeight = texture_height;

	{
		GLint max_texture_size = 0;
		glGetIntegerv (GL_MAX_TEXTURE_SIZE, &max_texture_size);
		if (max_texture_size < texture_width ||
				max_texture_size < texture_height)
		{
			log_add (log_Error, "OpenGL maximum texture size %d is too small "
					"for the %dx%d native-resolution screen texture.",
					max_texture_size, texture_width, texture_height);
			return -1;
		}
	}
	
	glViewport (0, 0, ScreenWidthActual, ScreenHeightActual);
	glClearColor (0,0,0,0);
	glClear (GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
	SDL_GL_SwapBuffers ();
	glClear (GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
	glDisable (GL_DITHER);
	glDepthMask(GL_FALSE);

	for (i = 0; i < TFB_GFX_NUMSCREENS; i++)
	{
		if (!GL_Screens[i].active)
			continue;
		glGenTextures (1, &GL_Screens[i].texture);
		glBindTexture (GL_TEXTURE_2D, GL_Screens[i].texture);
		glPixelStorei (GL_UNPACK_ALIGNMENT, 1);
		glTexParameterf (GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP);
		glTexParameterf (GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP);
		glTexImage2D (GL_TEXTURE_2D, 0, GL_RGB, texture_width,
			texture_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, 0);
	}

	return 0;
}

int
TFB_GL_InitGraphics (int driver, int flags, int width, int height, unsigned int resolutionFactor, BOOLEAN forceAspectRatio)  // JMS_GFX: Added resolutionFactor
{
	char VideoName[256];

	log_add (log_Info, "Initializing SDL with OpenGL support.");

	SDL_VideoDriverName (VideoName, sizeof (VideoName));
	log_add (log_Info, "SDL driver used: %s", VideoName);
	log_add (log_Info, "SDL initialized.");
	log_add (log_Info, "Initializing Screen.");

	ScreenWidth =  (320 << resolutionFactor); // JMS_GFX
	ScreenHeight = (240 << resolutionFactor); // JMS_GFX

	if (TFB_GL_ConfigureVideo (driver, flags, width, height, 0, resolutionFactor, forceAspectRatio)) 
	{
		log_add (log_Fatal, "Could not initialize video: "
				"no fallback at start of program!");
		exit (EXIT_FAILURE);
	}	 

	// Initialize scalers (let them precompute whatever)
	Scale_Init ();

	return 0;
}

void TFB_GL_UploadTransitionScreen (void)
{
	GL_Screens[TFB_SCREEN_TRANSITION].updated.x = 0;
	GL_Screens[TFB_SCREEN_TRANSITION].updated.y = 0;
	GL_Screens[TFB_SCREEN_TRANSITION].updated.w = ScreenWidth;
	GL_Screens[TFB_SCREEN_TRANSITION].updated.h = ScreenHeight;
	GL_Screens[TFB_SCREEN_TRANSITION].dirty = TRUE;
}

void
TFB_GL_ScanLines (void)
{
	int y;

	glDisable (GL_TEXTURE_2D);
	glEnable (GL_BLEND);
	glBlendFunc (GL_DST_COLOR, GL_ZERO);
	glColor3f (0.85f, 0.85f, 0.85f);
	for (y = 0; y < ScreenHeightActual; y += 2)
	{
		glBegin (GL_LINES);
		glVertex2i (0, y);
		glVertex2i (ScreenWidthActual, y);
		glEnd ();
	}

	glBlendFunc (GL_DST_COLOR, GL_ONE);
	glColor3f (0.2f, 0.2f, 0.2f);
	for (y = 1; y < ScreenHeightActual; y += 2)
	{
		glBegin (GL_LINES);
		glVertex2i (0, y);
		glVertex2i (ScreenWidthActual, y);
		glEnd ();
	}
}

static void
TFB_GL_DrawQuad (SDL_Rect *r)
{
	BOOLEAN keep_aspect_ratio = optKeepAspectRatio;
	int x1 = 0, y1 = 0, x2 = ScreenWidthActual, y2 = ScreenHeightActual;
	int sx = 0, sy = 0;
	int sw, sh;
	float sx_multiplier = 1;
	float sy_multiplier = 1;

	if (keep_aspect_ratio)
	{
		float threshold = 0.75f;
		float ratio = ScreenHeightActual / (float)ScreenWidthActual;

		if (ratio > threshold)
		{
			// screen is narrower than 4:3
			int height = (int)(ScreenWidthActual * threshold);
			y1 = (ScreenHeightActual - height) / 2;
			y2 = ScreenHeightActual - y1;

			if (r != NULL)
			{
				sx_multiplier = ScreenWidthActual / (float)ScreenWidth;
				sy_multiplier = height / (float)ScreenHeight;
				sx = (int)(r->x * sx_multiplier);
				sy = (int)(((ScreenHeight - (r->y + r->h)) * sy_multiplier) + y1);
			}
		}
		else if (ratio < threshold)
		{
			// screen is wider than 4:3
			int width = (int)(ScreenHeightActual / threshold);
			x1 = (ScreenWidthActual - width) / 2;
			x2 = ScreenWidthActual - x1;

			if (r != NULL)
			{
				sx_multiplier = width / (float)ScreenWidth;
				sy_multiplier = ScreenHeightActual / (float)ScreenHeight;
				sx = (int)((r->x * sx_multiplier) + x1);
				sy = (int)((ScreenHeight - (r->y + r->h)) * sy_multiplier);
			}
		}
		else
		{
			// screen is 4:3
			keep_aspect_ratio = 0;
		}
	}

	if (r != NULL)
	{
		if (!keep_aspect_ratio)
		{
			sx_multiplier = ScreenWidthActual / (float)ScreenWidth;
			sy_multiplier = ScreenHeightActual / (float)ScreenHeight;
			sx = (int)(r->x * sx_multiplier);
			sy = (int)((ScreenHeight - (r->y + r->h)) * sy_multiplier);
		}
		sw = (int)(r->w * sx_multiplier);
		sh = (int)(r->h * sy_multiplier);
		glScissor (sx, sy, sw, sh);
		glEnable (GL_SCISSOR_TEST);
	}
	
	glBegin (GL_TRIANGLE_FAN);
	glTexCoord2f (0, 0);
	glVertex2i (x1, y1);
	glTexCoord2f (ScreenWidth / 512.0f, 0);
	glVertex2i (x2, y1);	
	glTexCoord2f (ScreenWidth / 512.0f, ScreenHeight / 256.0f);
	glVertex2i (x2, y2);
	glTexCoord2f (0, ScreenHeight / 256.0f);
	glVertex2i (x1, y2);
	glEnd ();
	if (r != NULL)
	{
		glDisable (GL_SCISSOR_TEST);
	}
}

static void
TFB_GL_DrawQuad_2x (SDL_Rect *r)
{
	BOOLEAN keep_aspect_ratio = optKeepAspectRatio;
	int x1 = 0, y1 = 0, x2 = ScreenWidthActual, y2 = ScreenHeightActual;
	int sx = 0, sy = 0;
	int sw, sh;
	float sx_multiplier = 1;
	float sy_multiplier = 1;
	
	if (keep_aspect_ratio)
	{
		float threshold = 0.75f;
		float ratio = ScreenHeightActual / (float)ScreenWidthActual;
		
		if (ratio > threshold)
		{
			// screen is narrower than 4:3
			int height = (int)(ScreenWidthActual * threshold);
			y1 = (ScreenHeightActual - height) / 2;
			y2 = ScreenHeightActual - y1;
			
			if (r != NULL)
			{
				sx_multiplier = ScreenWidthActual / (float)ScreenWidth;
				sy_multiplier = height / (float)ScreenHeight;
				sx = (int)(r->x * sx_multiplier);
				sy = (int)(((ScreenHeight - (r->y + r->h)) * sy_multiplier) + y1);
			}
		}
		else if (ratio < threshold)
		{
			// screen is wider than 4:3
			int width = (int)(ScreenHeightActual / threshold);
			x1 = (ScreenWidthActual - width) / 2;
			x2 = ScreenWidthActual - x1;
			
			if (r != NULL)
			{
				sx_multiplier = width / (float)ScreenWidth;
				sy_multiplier = ScreenHeightActual / (float)ScreenHeight;
				sx = (int)((r->x * sx_multiplier) + x1);
				sy = (int)((ScreenHeight - (r->y + r->h)) * sy_multiplier);
			}
		}
		else
		{
			// screen is 4:3
			keep_aspect_ratio = 0;
		}
	}
	
	if (r != NULL)
	{
		if (!keep_aspect_ratio)
		{
			sx_multiplier = ScreenWidthActual / (float)ScreenWidth;
			sy_multiplier = ScreenHeightActual / (float)ScreenHeight;
			sx = (int)(r->x * sx_multiplier);
			sy = (int)((ScreenHeight - (r->y + r->h)) * sy_multiplier);
		}
		sw = (int)(r->w * sx_multiplier);
		sh = (int)(r->h * sy_multiplier);
		glScissor (sx, sy, sw, sh);
		glEnable (GL_SCISSOR_TEST);
	}
	
	glBegin (GL_TRIANGLE_FAN);
	glTexCoord2f (0, 0);
	glVertex2i (x1, y1);
	glTexCoord2f (ScreenWidth / 1024.0f, 0);
	glVertex2i (x2, y1);	
	glTexCoord2f (ScreenWidth / 1024.0f, ScreenHeight / 512.0f);
	glVertex2i (x2, y2);
	glTexCoord2f (0, ScreenHeight / 512.0f);
	glVertex2i (x1, y2);
	glEnd ();
	if (r != NULL)
	{
		glDisable (GL_SCISSOR_TEST);
	}
}

static void
TFB_GL_DrawQuad_4x (SDL_Rect *r)
{
	BOOLEAN keep_aspect_ratio = optKeepAspectRatio;
	int x1 = 0, y1 = 0, x2 = ScreenWidthActual, y2 = ScreenHeightActual;
	int sx = 0, sy = 0;
	int sw, sh;
	float sx_multiplier = 1;
	float sy_multiplier = 1;
	
	if (keep_aspect_ratio)
	{
		float threshold = 0.75f;
		float ratio = ScreenHeightActual / (float)ScreenWidthActual;
		
		if (ratio > threshold)
		{
			// screen is narrower than 4:3
			int height = (int)(ScreenWidthActual * threshold);
			y1 = (ScreenHeightActual - height) / 2;
			y2 = ScreenHeightActual - y1;
			
			if (r != NULL)
			{
				sx_multiplier = ScreenWidthActual / (float)ScreenWidth;
				sy_multiplier = height / (float)ScreenHeight;
				sx = (int)(r->x * sx_multiplier);
				sy = (int)(((ScreenHeight - (r->y + r->h)) * sy_multiplier) + y1);
			}
		}
		else if (ratio < threshold)
		{
			// screen is wider than 4:3
			int width = (int)(ScreenHeightActual / threshold);
			x1 = (ScreenWidthActual - width) / 2;
			x2 = ScreenWidthActual - x1;
			
			if (r != NULL)
			{
				sx_multiplier = width / (float)ScreenWidth;
				sy_multiplier = ScreenHeightActual / (float)ScreenHeight;
				sx = (int)((r->x * sx_multiplier) + x1);
				sy = (int)((ScreenHeight - (r->y + r->h)) * sy_multiplier);
			}
		}
		else
		{
			// screen is 4:3
			keep_aspect_ratio = 0;
		}
	}
	
	if (r != NULL)
	{
		if (!keep_aspect_ratio)
		{
			sx_multiplier = ScreenWidthActual / (float)ScreenWidth;
			sy_multiplier = ScreenHeightActual / (float)ScreenHeight;
			sx = (int)(r->x * sx_multiplier);
			sy = (int)((ScreenHeight - (r->y + r->h)) * sy_multiplier);
		}
		sw = (int)(r->w * sx_multiplier);
		sh = (int)(r->h * sy_multiplier);
		glScissor (sx, sy, sw, sh);
		glEnable (GL_SCISSOR_TEST);
	}
	
	glBegin (GL_TRIANGLE_FAN);
	glTexCoord2f (0, 0);
	glVertex2i (x1, y1);
	glTexCoord2f (ScreenWidth / (float)ScreenTextureWidth, 0);
	glVertex2i (x2, y1);	
	glTexCoord2f (ScreenWidth / (float)ScreenTextureWidth,
			ScreenHeight / (float)ScreenTextureHeight);
	glVertex2i (x2, y2);
	glTexCoord2f (0, ScreenHeight / (float)ScreenTextureHeight);
	glVertex2i (x1, y2);
	glEnd ();
	if (r != NULL)
	{
		glDisable (GL_SCISSOR_TEST);
	}
}

static void
TFB_GL_Preprocess (int force_full_redraw, int transition_amount, int fade_amount)
{
	glMatrixMode (GL_PROJECTION);
	glLoadIdentity ();
	glOrtho (0,ScreenWidthActual,ScreenHeightActual, 0, -1, 1);
	glMatrixMode (GL_MODELVIEW);
	glLoadIdentity ();
	if (optKeepAspectRatio)
		glClear (GL_COLOR_BUFFER_BIT);

	(void) transition_amount;
	(void) fade_amount;

	if (force_full_redraw == TFB_REDRAW_YES)
	{
		GL_Screens[TFB_SCREEN_MAIN].updated.x = 0;
		GL_Screens[TFB_SCREEN_MAIN].updated.y = 0;
		GL_Screens[TFB_SCREEN_MAIN].updated.w = ScreenWidth;
		GL_Screens[TFB_SCREEN_MAIN].updated.h = ScreenHeight;
		GL_Screens[TFB_SCREEN_MAIN].dirty = TRUE;
	}
	else if (TFB_BBox.valid)
	{
		GL_Screens[TFB_SCREEN_MAIN].updated.x = TFB_BBox.region.corner.x;
		GL_Screens[TFB_SCREEN_MAIN].updated.y = TFB_BBox.region.corner.y;
		GL_Screens[TFB_SCREEN_MAIN].updated.w = TFB_BBox.region.extent.width;
		GL_Screens[TFB_SCREEN_MAIN].updated.h = TFB_BBox.region.extent.height;
		GL_Screens[TFB_SCREEN_MAIN].dirty = TRUE;
	}
}

static void
TFB_GL_Unscaled_ScreenLayer (SCREEN screen, Uint8 a, SDL_Rect *rect)
{
	glBindTexture (GL_TEXTURE_2D, GL_Screens[screen].texture);
	glTexEnvf (GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

	if (GL_Screens[screen].dirty)
	{
		int PitchWords = SDL_Screens[screen]->pitch / 4;
		glPixelStorei (GL_UNPACK_ROW_LENGTH, PitchWords);
		/* Matrox OpenGL drivers do not handle GL_UNPACK_SKIP_*
		   correctly */
		glPixelStorei (GL_UNPACK_SKIP_ROWS, 0);
		glPixelStorei (GL_UNPACK_SKIP_PIXELS, 0);
		SDL_LockSurface (SDL_Screens[screen]);
		glTexSubImage2D (GL_TEXTURE_2D, 0, GL_Screens[screen].updated.x, 
				GL_Screens[screen].updated.y,
				GL_Screens[screen].updated.w, 
				GL_Screens[screen].updated.h,
				GL_RGBA, GL_UNSIGNED_BYTE,
				(Uint32 *)SDL_Screens[screen]->pixels +
					(GL_Screens[screen].updated.y * PitchWords + 
					GL_Screens[screen].updated.x));
		SDL_UnlockSurface (SDL_Screens[screen]);
		GL_Screens[screen].dirty = FALSE;
	}

	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, ScreenFilterMode);
	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, ScreenFilterMode);
	glEnable (GL_TEXTURE_2D);

	if (a == 255)
	{
		glDisable (GL_BLEND);
		glColor4f (1, 1, 1, 1);
	}
	else
	{
		float a_f = a / 255.0f;
		glBlendFunc (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
		glEnable (GL_BLEND);
		glColor4f (1, 1, 1, a_f);
	}
	
	TFB_GL_DrawQuad (rect);
}

static void
TFB_GL_Unscaled_ScreenLayer_2x (SCREEN screen, Uint8 a, SDL_Rect *rect)
{
	glBindTexture (GL_TEXTURE_2D, GL_Screens[screen].texture);
	glTexEnvf (GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);
	
	if (GL_Screens[screen].dirty)
	{
		int PitchWords = SDL_Screens[screen]->pitch / 4;
		glPixelStorei (GL_UNPACK_ROW_LENGTH, PitchWords);
		/* Matrox OpenGL drivers do not handle GL_UNPACK_SKIP_*
		 correctly */
		glPixelStorei (GL_UNPACK_SKIP_ROWS, 0);
		glPixelStorei (GL_UNPACK_SKIP_PIXELS, 0);
		SDL_LockSurface (SDL_Screens[screen]);
		glTexSubImage2D (GL_TEXTURE_2D, 0, GL_Screens[screen].updated.x, 
						 GL_Screens[screen].updated.y,
						 GL_Screens[screen].updated.w, 
						 GL_Screens[screen].updated.h,
						 GL_RGBA, GL_UNSIGNED_BYTE,
						 (Uint32 *)SDL_Screens[screen]->pixels +
						 (GL_Screens[screen].updated.y * PitchWords + 
						  GL_Screens[screen].updated.x));
		SDL_UnlockSurface (SDL_Screens[screen]);
		GL_Screens[screen].dirty = FALSE;
	}
	
	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, ScreenFilterMode);
	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, ScreenFilterMode);
	glEnable (GL_TEXTURE_2D);
	
	if (a == 255)
	{
		glDisable (GL_BLEND);
		glColor4f (1, 1, 1, 1);
	}
	else
	{
		float a_f = a / 255.0f;
		glBlendFunc (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
		glEnable (GL_BLEND);
		glColor4f (1, 1, 1, a_f);
	}
	
	TFB_GL_DrawQuad_2x (rect);
}

static void
TFB_GL_Unscaled_ScreenLayer_4x (SCREEN screen, Uint8 a, SDL_Rect *rect)
{
	glBindTexture (GL_TEXTURE_2D, GL_Screens[screen].texture);
	glTexEnvf (GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);
	
	if (GL_Screens[screen].dirty)
	{
		int PitchWords = SDL_Screens[screen]->pitch / 4;
		glPixelStorei (GL_UNPACK_ROW_LENGTH, PitchWords);
		/* Matrox OpenGL drivers do not handle GL_UNPACK_SKIP_*
		 correctly */
		glPixelStorei (GL_UNPACK_SKIP_ROWS, 0);
		glPixelStorei (GL_UNPACK_SKIP_PIXELS, 0);
		SDL_LockSurface (SDL_Screens[screen]);
		glTexSubImage2D (GL_TEXTURE_2D, 0, GL_Screens[screen].updated.x, 
						 GL_Screens[screen].updated.y,
						 GL_Screens[screen].updated.w, 
						 GL_Screens[screen].updated.h,
						 GL_RGBA, GL_UNSIGNED_BYTE,
						 (Uint32 *)SDL_Screens[screen]->pixels +
						 (GL_Screens[screen].updated.y * PitchWords + 
						  GL_Screens[screen].updated.x));
		SDL_UnlockSurface (SDL_Screens[screen]);
		GL_Screens[screen].dirty = FALSE;
	}
	
	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, ScreenFilterMode);
	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, ScreenFilterMode);
	glEnable (GL_TEXTURE_2D);
	
	if (a == 255)
	{
		glDisable (GL_BLEND);
		glColor4f (1, 1, 1, 1);
	}
	else
	{
		float a_f = a / 255.0f;
		glBlendFunc (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
		glEnable (GL_BLEND);
		glColor4f (1, 1, 1, a_f);
	}
	
	TFB_GL_DrawQuad_4x (rect);
}

static void
TFB_GL_Scaled_ScreenLayer (SCREEN screen, Uint8 a, SDL_Rect *rect)
{
	glBindTexture (GL_TEXTURE_2D, GL_Screens[screen].texture);
	glTexEnvf (GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE);

	if (GL_Screens[screen].dirty)
	{
		int PitchWords = GL_Screens[screen].scaled->pitch / 4;
		scaler (SDL_Screens[screen], GL_Screens[screen].scaled, &GL_Screens[screen].updated);
		glPixelStorei (GL_UNPACK_ROW_LENGTH, PitchWords);

		 /* Matrox OpenGL drivers do not handle GL_UNPACK_SKIP_*
		    correctly */
		glPixelStorei (GL_UNPACK_SKIP_ROWS, 0);
		glPixelStorei (GL_UNPACK_SKIP_PIXELS, 0);
		SDL_LockSurface (GL_Screens[screen].scaled);
		glTexSubImage2D (GL_TEXTURE_2D, 0, GL_Screens[screen].updated.x * 2, 
				GL_Screens[screen].updated.y * 2,
				GL_Screens[screen].updated.w * 2, 
				GL_Screens[screen].updated.h * 2,
				GL_RGBA, GL_UNSIGNED_BYTE,
				(Uint32 *)GL_Screens[screen].scaled->pixels +
				(GL_Screens[screen].updated.y * 2 * PitchWords + 
				GL_Screens[screen].updated.x * 2));
		SDL_UnlockSurface (GL_Screens[screen].scaled);
		GL_Screens[screen].dirty = FALSE;
	}

	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, ScreenFilterMode);
	glTexParameteri (GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, ScreenFilterMode);
	glEnable (GL_TEXTURE_2D);

	if (a == 255)
	{
		glDisable (GL_BLEND);
		glColor4f (1, 1, 1, 1);
	}
	else
	{
		float a_f = a / 255.0f;
		glBlendFunc (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
		glEnable (GL_BLEND);
		glColor4f (1, 1, 1, a_f);
	}
	
	TFB_GL_DrawQuad (rect);
}

static void
TFB_GL_ColorLayer (Uint8 r, Uint8 g, Uint8 b, Uint8 a, SDL_Rect *rect)
{
	float r_f = r / 255.0f;
	float g_f = g / 255.0f;
	float b_f = b / 255.0f;
	float a_f = a / 255.0f;
	glColor4f(r_f, g_f, b_f, a_f);

	glDisable (GL_TEXTURE_2D);
	if (a != 255)
	{
		glBlendFunc (GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
		glEnable (GL_BLEND);
	}
	else
	{
		glDisable (GL_BLEND);
	}
	
	TFB_GL_DrawQuad (rect);
}

static SDL_Surface *
TFB_GL_CaptureFramebuffer (void)
{
	SDL_Surface *capture;
	Uint8 *temporary_row;
	Uint8 *top_row;
	Uint8 *bottom_row;
	int y;

	capture = SDL_CreateRGBSurface (SDL_SWSURFACE,
			ScreenWidthActual, ScreenHeightActual, 32,
			R_MASK, G_MASK, B_MASK, A_MASK);
	if (capture == NULL)
		return NULL;

	glReadBuffer (GL_BACK);
	glReadPixels (0, 0, ScreenWidthActual, ScreenHeightActual,
			GL_RGBA, GL_UNSIGNED_BYTE, capture->pixels);

	/* OpenGL's origin is at the lower left, while SDL bitmap rows start at
	 * the upper left.  Flip the captured frame before saving or copying it. */
	temporary_row = (Uint8 *) SDL_malloc (capture->pitch);
	if (temporary_row == NULL)
	{
		SDL_FreeSurface (capture);
		return NULL;
	}
	for (y = 0; y < capture->h / 2; ++y)
	{
		top_row = (Uint8 *) capture->pixels + y * capture->pitch;
		bottom_row = (Uint8 *) capture->pixels +
				(capture->h - y - 1) * capture->pitch;
		memcpy (temporary_row, top_row, capture->pitch);
		memcpy (top_row, bottom_row, capture->pitch);
		memcpy (bottom_row, temporary_row, capture->pitch);
	}
	SDL_free (temporary_row);
	return capture;
}

static void
TFB_GL_SaveUserScreenshot (SDL_Surface *capture)
{
	const char *config_path;
	char screenshot_dir[PATH_MAX];
	char screenshot_path[PATH_MAX];
	time_t now;
	struct tm *local_now;
	char timestamp[32];
	int result;
	BOOLEAN copied = FALSE;

	config_path = getenv ("UQM_CONFIG_DIR");
	if (config_path == NULL || *config_path == '\0')
		config_path = ".";
	result = snprintf (screenshot_dir, sizeof (screenshot_dir),
			"%s/screenshots", config_path);
	if (result < 0 || result >= (int) sizeof (screenshot_dir) ||
			mkdirhier (screenshot_dir) == -1)
	{
		log_add (log_Warning, "Could not create the screenshot directory");
		return;
	}

	now = time (NULL);
	local_now = localtime (&now);
	if (local_now == NULL ||
			strftime (timestamp, sizeof (timestamp), "%Y%m%d-%H%M%S",
					local_now) == 0)
		strcpy (timestamp, "unknown-time");
	result = snprintf (screenshot_path, sizeof (screenshot_path),
			"%s/uqm-%s-%03u.bmp", screenshot_dir, timestamp,
			(unsigned int) (SDL_GetTicks () % 1000));
	if (result < 0 || result >= (int) sizeof (screenshot_path))
	{
		log_add (log_Warning, "The screenshot path is too long");
		return;
	}

#ifdef WIN32
	copied = TFB_Win32_CopyRGBAToClipboard (
			(const unsigned char *) capture->pixels, capture->w, capture->h,
			capture->pitch) != 0;
#endif
	if (SDL_SaveBMP (capture, screenshot_path) == 0)
		log_add (log_Info, "Saved screenshot to '%s'%s", screenshot_path,
				copied ? " and copied it to the clipboard" : "");
	else
		log_add (log_Warning, "Could not save screenshot: %s",
				SDL_GetError ());
}

static void
TFB_GL_Postprocess (void)
{
	static unsigned int qa_capture_frame = 0;
	const char *qa_capture_path = getenv ("UQM_QA_CAPTURE");
	SDL_Surface *capture;

	if (GfxFlags & TFB_GFXFLAGS_SCANLINES)
		TFB_GL_ScanLines ();

	/* Optional framebuffer capture for automated visual smoke tests.  Reading
	 * from OpenGL directly also works with exclusive fullscreen drivers that
	 * Windows.Graphics.Capture and GDI cannot observe. */
	if (qa_capture_path && *qa_capture_path &&
			qa_capture_frame++ >= 30 && qa_capture_frame % 300 == 0)
	{
		capture = TFB_GL_CaptureFramebuffer ();
		if (capture)
		{
			if (SDL_SaveBMP (capture, qa_capture_path) == 0)
				log_add (log_Info, "Saved QA framebuffer capture to '%s'",
						qa_capture_path);
			else
				log_add (log_Warning, "Could not save QA framebuffer capture: %s",
						SDL_GetError ());
			SDL_FreeSurface (capture);
		}
	}

	if (ScreenshotRequested)
	{
		ScreenshotRequested = FALSE;
		capture = TFB_GL_CaptureFramebuffer ();
		if (capture != NULL)
		{
			TFB_GL_SaveUserScreenshot (capture);
			SDL_FreeSurface (capture);
		}
		else
			log_add (log_Warning, "Could not capture the OpenGL framebuffer");
	}

	SDL_GL_SwapBuffers ();
}	

#endif

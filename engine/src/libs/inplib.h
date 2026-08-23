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

#ifndef _INPLIB_H
#define _INPLIB_H

#include <stddef.h>
#include "libs/compiler.h"
#include "libs/uio.h"
#include "libs/unicode.h"


extern BOOLEAN AnyButtonPress (BOOLEAN DetectSpecial);

extern void TFB_ResetControls (void);

/*
 * Not used right now
extern BOOLEAN FindMouse (void);
extern void MoveMouse (SWORD x, SWORD y);
extern BYTE LocateMouse (SWORD *px, SWORD *py);
*/

extern volatile int MouseButtonDown;
extern volatile int QuitPosted;
extern volatile int GameActive;

/*
 * Thread-safe mouse state in the game's logical 4:3 coordinate space.
 * Button numbers intentionally match SDL 1.2 (and the values stored in
 * last_button); button_mask uses one bit per button, starting at bit zero.
 */
enum
{
	TFB_MOUSE_BUTTON_NONE = 0,
	TFB_MOUSE_BUTTON_LEFT = 1,
	TFB_MOUSE_BUTTON_MIDDLE = 2,
	TFB_MOUSE_BUTTON_RIGHT = 3,
	TFB_MOUSE_BUTTON_WHEEL_UP = 4,
	TFB_MOUSE_BUTTON_WHEEL_DOWN = 5,
	TFB_MOUSE_BUTTON_X1 = 6,
	TFB_MOUSE_BUTTON_X2 = 7
};

#define TFB_MOUSE_BUTTON_MASK(button) (1U << ((button) - 1))

typedef struct tfb_mouse_state
{
	SWORD x;
	SWORD y;
	BOOLEAN inside_viewport;
	SWORD press_x;
	SWORD press_y;
	BOOLEAN press_inside_viewport;
	unsigned int button_mask;
	unsigned int last_button;
	unsigned int motion_generation;
	unsigned int press_generation;
} TFB_MOUSE_STATE;

/* Returns FALSE before input initialization or when state cannot be locked. */
extern BOOLEAN TFB_GetMouseState (TFB_MOUSE_STATE *state);

/* Functions for dealing with Character Mode */

void EnterCharacterMode (void);
void ExitCharacterMode (void);
UniChar GetNextCharacter (void);
UniChar GetLastCharacter (void);

/* Interrogating the current key configuration */

void InterrogateInputState (int template, int control, int index, char *buffer, int maxlen);
void RemoveInputState (int template, int control, int index);
void RebindInputState (int template, int control, int index);

void SaveKeyConfiguration (uio_DirHandle *path, const char *fname);

/* Separate inputs into frames for dealing with very fast inputs */

void BeginInputFrame (void);

#endif /* _INPLIB_H */

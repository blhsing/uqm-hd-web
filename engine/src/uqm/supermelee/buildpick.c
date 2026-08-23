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

#include "buildpick.h"

#include "../controls.h"
#include "../colors.h"
#include "../fmv.h"
#include "../master.h"
#include "../setup.h"
#include "../sounds.h"
#include "libs/gfxlib.h"
#include "libs/inplib.h"

static FRAME BuildPickFrame;

#define BUILD_PICK_STATS_WIDTH (149 << RESOLUTION_FACTOR)
#define BUILD_PICK_STATS_HEIGHT (44 << RESOLUTION_FACTOR)
#define BUILD_PICK_STATS_GAP (2 << RESOLUTION_FACTOR)

/* Coordinates of the two vertical action labels in the 4x picker artwork.
 * Scaling from the actual frame dimensions keeps their hit targets aligned
 * with the independently sized 1x, 2x, and 4x resources. */
#define BUILD_PICK_REFERENCE_WIDTH 508
#define BUILD_PICK_REFERENCE_HEIGHT 465
#define BUILD_PICK_ACTION_TOP 74
#define BUILD_PICK_ACTION_BOTTOM 445
#define BUILD_PICK_CONFIRM_LEFT 13
#define BUILD_PICK_CONFIRM_RIGHT 67
#define BUILD_PICK_INFO_LEFT 440
#define BUILD_PICK_INFO_RIGHT 495

typedef enum
{
	BUILD_PICK_ACTION_NONE,
	BUILD_PICK_ACTION_CONFIRM,
	BUILD_PICK_ACTION_INFO
} BUILD_PICK_ACTION;

static void
BuildPick_syncMouseState (MELEE_STATE *pMS)
{
	TFB_MOUSE_STATE mouse;

	pMS->mouseMotionGeneration = 0;
	pMS->mousePressGeneration = 0;
	if (TFB_GetMouseState (&mouse))
	{
		pMS->mouseMotionGeneration = mouse.motion_generation;
		pMS->mousePressGeneration = mouse.press_generation;
	}
}

void
BuildBuildPickFrame (void)
{
	STAMP	s;
	RECT    r;
	COUNT   i;
	CONTEXT OldContext = SetContext (OffScreenContext);
	
	// create team building ship selection box
	s.origin.x = 0;
	s.origin.y = 0;
	s.frame = SetAbsFrameIndex (MeleeFrame, 27);
			// 5x5 grid of ships to pick from
	GetFrameRect (s.frame, &r);

	BuildPickFrame = CaptureDrawable (CreateDrawable (
			WANT_PIXMAP, r.extent.width, r.extent.height, 1));
	SetContextFGFrame (BuildPickFrame);
	SetFrameHot (s.frame, MAKE_HOT_SPOT (0, 0));
	DrawStamp (&s);

	for (i = 0; i < NUM_PICK_COLS * NUM_PICK_ROWS; ++i)
		DrawPickIcon (i, true);

	SetContext (OldContext);
}

void
DestroyBuildPickFrame (void)
{
	DestroyDrawable (ReleaseDrawable (BuildPickFrame));
	BuildPickFrame = 0;
}

// Draw a ship icon in the ship selection popup.
void
DrawPickIcon (MeleeShip ship, bool DrawErase)
{
	STAMP s;
	RECT r;

	GetFrameRect (BuildPickFrame, &r);

	s.origin.x = r.corner.x + (20 << RESOLUTION_FACTOR) + (ship % NUM_PICK_COLS) * (18 << RESOLUTION_FACTOR) - RES_CASE(0,0,2); // JMS_GFX
	s.origin.y = r.corner.y + (5 << RESOLUTION_FACTOR) + (ship / NUM_PICK_COLS) * (18 << RESOLUTION_FACTOR); // JMS_GFX
	s.frame = GetShipIconsFromIndex (ship);
	if (DrawErase)
	{	// draw icon
		DrawStamp (&s);
	}
	else
	{	// erase icon
		Color OldColor;

		OldColor = SetContextForeGroundColor (BLACK_COLOR);
		DrawFilledStamp (&s);
		SetContextForeGroundColor (OldColor);
	}
}

static void
GetBuildPickPopupRect (RECT *r)
{
	GetFrameRect (BuildPickFrame, r);
}

static void
GetBuildPickStatsRect (RECT *r)
{
	RECT popupRect;
	COORD rightLimit;

	GetBuildPickPopupRect (&popupRect);
	r->extent.width = BUILD_PICK_STATS_WIDTH;
	r->extent.height = BUILD_PICK_STATS_HEIGHT;
	r->corner.x = popupRect.corner.x
			+ ((popupRect.extent.width - r->extent.width) >> 1);
	rightLimit = SCREEN_WIDTH - (2 << RESOLUTION_FACTOR);
	if (r->corner.x < (2 << RESOLUTION_FACTOR))
		r->corner.x = 2 << RESOLUTION_FACTOR;
	else if (r->corner.x + r->extent.width > rightLimit)
		r->corner.x = rightLimit - r->extent.width;

	/* The card is adjacent to, never on top of, the 5x5 ship grid. */
	r->corner.y = popupRect.corner.y + popupRect.extent.height
			+ BUILD_PICK_STATS_GAP;
	if (r->corner.y + r->extent.height > SCREEN_HEIGHT)
		r->corner.y = popupRect.corner.y - BUILD_PICK_STATS_GAP
				- r->extent.height;
}

// Pre: the called holds the GraphicsLock
void
DrawPickFrame (MELEE_STATE *pMS)
{
	RECT r, r0, r1, ship_r;
	STAMP s;
				
	GetShipBox (&r0, 0, 0, 0),
	GetShipBox (&r1, 1, NUM_MELEE_ROWS - 1, NUM_MELEE_COLUMNS - 1),
	BoxUnion (&r0, &r1, &ship_r);

	s.frame = SetAbsFrameIndex (BuildPickFrame, 0);
	GetFrameRect (s.frame, &r);
	r.corner.x = -(ship_r.corner.x
			+ ((ship_r.extent.width - r.extent.width) >> 1));
	if (pMS->side)
		r.corner.y = -ship_r.corner.y;
	else
		r.corner.y = -(ship_r.corner.y
				+ (ship_r.extent.height - r.extent.height));
	SetFrameHot (s.frame, MAKE_HOT_SPOT (r.corner.x, r.corner.y));
	s.origin.x = 0;
	s.origin.y = 0;
	DrawStamp (&s);
	DrawMeleeShipStrings (pMS, pMS->currentShip);
	GetBuildPickStatsRect (&r);
	DrawMeleeShipStatsCard (pMS->currentShip, &r, NULL);
}

void
GetBuildPickFrameRect (RECT *r)
{
	RECT popupRect;
	RECT statsRect;

	GetBuildPickPopupRect (&popupRect);
	GetBuildPickStatsRect (&statsRect);
	BoxUnion (&popupRect, &statsRect, r);
}

static void
BuildPick_changeSelection (MELEE_STATE *pMS, MeleeShip newSelectedShip)
{
	if (newSelectedShip == pMS->currentShip)
		return;

	LockMutex (GraphicsLock);
	DrawPickIcon (pMS->currentShip, true);
	pMS->currentShip = newSelectedShip;
	DrawMeleeShipStrings (pMS, newSelectedShip);
	{
		RECT r;
		GetBuildPickStatsRect (&r);
		DrawMeleeShipStatsCard (newSelectedShip, &r, NULL);
	}
	UnlockMutex (GraphicsLock);
}

static BOOLEAN
BuildPick_findShipAt (SWORD mouseX, SWORD mouseY, MeleeShip *result)
{
	RECT popupRect;
	POINT point;
	MeleeShip ship;

	GetBuildPickPopupRect (&popupRect);
	point.x = mouseX;
	point.y = mouseY;
	for (ship = 0; ship < NUM_PICK_COLS * NUM_PICK_ROWS; ++ship)
	{
		POINT origin;
		RECT iconRect;
		FRAME icon = GetShipIconsFromIndex (ship);

		origin.x = popupRect.corner.x + (20 << RESOLUTION_FACTOR)
				+ (ship % NUM_PICK_COLS) * (18 << RESOLUTION_FACTOR)
				- RES_CASE(0,0,2);
		origin.y = popupRect.corner.y + (5 << RESOLUTION_FACTOR)
				+ (ship / NUM_PICK_COLS) * (18 << RESOLUTION_FACTOR);
		if (GetFrameRect (icon, &iconRect))
		{
			iconRect.corner.x += origin.x;
			iconRect.corner.y += origin.y;
			if (pointWithinRect (iconRect, point))
			{
				*result = ship;
				return TRUE;
			}
		}
	}

	return FALSE;
}

static COORD
BuildPick_scaleActionCoordinate (COORD value, COORD extent, COORD reference)
{
	return (COORD)(((SDWORD)value * extent + (reference >> 1)) / reference);
}

static BOOLEAN
BuildPick_findActionAt (SWORD mouseX, SWORD mouseY,
		BUILD_PICK_ACTION *result)
{
	RECT popupRect;
	RECT actionRect;
	POINT point;
	COORD top;
	COORD bottom;
	COORD left;
	COORD right;

	GetBuildPickPopupRect (&popupRect);
	point.x = mouseX;
	point.y = mouseY;
	top = BuildPick_scaleActionCoordinate (BUILD_PICK_ACTION_TOP,
			popupRect.extent.height, BUILD_PICK_REFERENCE_HEIGHT);
	bottom = BuildPick_scaleActionCoordinate (BUILD_PICK_ACTION_BOTTOM,
			popupRect.extent.height, BUILD_PICK_REFERENCE_HEIGHT);
	actionRect.corner.y = popupRect.corner.y + top;
	actionRect.extent.height = bottom - top;

	left = BuildPick_scaleActionCoordinate (BUILD_PICK_CONFIRM_LEFT,
			popupRect.extent.width, BUILD_PICK_REFERENCE_WIDTH);
	right = BuildPick_scaleActionCoordinate (BUILD_PICK_CONFIRM_RIGHT,
			popupRect.extent.width, BUILD_PICK_REFERENCE_WIDTH);
	actionRect.corner.x = popupRect.corner.x + left;
	actionRect.extent.width = right - left;
	if (pointWithinRect (actionRect, point))
	{
		*result = BUILD_PICK_ACTION_CONFIRM;
		return TRUE;
	}

	left = BuildPick_scaleActionCoordinate (BUILD_PICK_INFO_LEFT,
			popupRect.extent.width, BUILD_PICK_REFERENCE_WIDTH);
	right = BuildPick_scaleActionCoordinate (BUILD_PICK_INFO_RIGHT,
			popupRect.extent.width, BUILD_PICK_REFERENCE_WIDTH);
	actionRect.corner.x = popupRect.corner.x + left;
	actionRect.extent.width = right - left;
	if (pointWithinRect (actionRect, point))
	{
		*result = BUILD_PICK_ACTION_INFO;
		return TRUE;
	}

	*result = BUILD_PICK_ACTION_NONE;
	return FALSE;
}

static BOOLEAN
BuildPick_processMouse (MELEE_STATE *pMS)
{
	TFB_MOUSE_STATE mouse;
	BOOLEAN newMotion;
	BOOLEAN newPress;
	MeleeShip hoveredShip;
	MeleeShip pressedShip;
	BOOLEAN leftPress;
	BUILD_PICK_ACTION pressedAction;

	if (!TFB_GetMouseState (&mouse))
		return FALSE;
	newMotion = mouse.motion_generation != pMS->mouseMotionGeneration;
	newPress = mouse.press_generation != pMS->mousePressGeneration;
	pMS->mouseMotionGeneration = mouse.motion_generation;
	pMS->mousePressGeneration = mouse.press_generation;
	if (!newMotion && !newPress)
		return FALSE;

	leftPress = newPress && mouse.last_button == TFB_MOUSE_BUTTON_LEFT;
	if (leftPress && mouse.press_inside_viewport &&
			BuildPick_findActionAt (mouse.press_x, mouse.press_y,
			&pressedAction))
	{
		if (pressedAction == BUILD_PICK_ACTION_CONFIRM)
		{
			pMS->buildPickConfirmed = true;
			PlayMenuSound (MENU_SOUND_SUCCESS);
			return TRUE;
		}
		if (pressedAction == BUILD_PICK_ACTION_INFO &&
				pMS->currentShip != MELEE_NONE)
		{
			DoShipSpin (pMS->currentShip, (MUSIC_REF) 0);
			/* Consume the click which closed the info page, otherwise a
			 * stationary pointer over this label would reopen it. */
			BuildPick_syncMouseState (pMS);
			return FALSE;
		}
	}
	else if (leftPress && mouse.press_inside_viewport &&
			BuildPick_findShipAt (mouse.press_x, mouse.press_y, &pressedShip))
	{
		if (pressedShip != pMS->currentShip)
		{
			BuildPick_changeSelection (pMS, pressedShip);
			PlayMenuSound (MENU_SOUND_MOVE);
		}
		pMS->buildPickConfirmed = true;
		PlayMenuSound (MENU_SOUND_SUCCESS);
		return TRUE;
	}

	if (mouse.inside_viewport &&
			BuildPick_findShipAt (mouse.x, mouse.y, &hoveredShip) &&
			hoveredShip != pMS->currentShip)
	{
		BuildPick_changeSelection (pMS, hoveredShip);
		PlayMenuSound (MENU_SOUND_MOVE);
	}

	return FALSE;
}

static BOOLEAN
DoPickShip (MELEE_STATE *pMS)
{
	DWORD TimeIn = GetTimeCounter ();

	/* Cancel any presses of the Pause key. */
	GamePaused = FALSE;

	if (GLOBAL (CurrentActivity) & CHECK_ABORT)
	{
		pMS->buildPickConfirmed = false;
		return FALSE;
	}

	SetMenuSounds (MENU_SOUND_ARROWS, MENU_SOUND_SELECT);
	if (BuildPick_processMouse (pMS))
		return FALSE;

	if (PulsedInputState.menu[KEY_MENU_SELECT] ||
			PulsedInputState.menu[KEY_MENU_CANCEL])
	{
		// Confirm selection or cancel.
		pMS->buildPickConfirmed = !PulsedInputState.menu[KEY_MENU_CANCEL];
		return FALSE;
	}
	
	if (PulsedInputState.menu[KEY_MENU_SPECIAL]
			&& (pMS->currentShip != MELEE_NONE))
	{
		// Show ship spin video.
		DoShipSpin (pMS->currentShip, (MUSIC_REF) 0);
		BuildPick_syncMouseState (pMS);
		return TRUE;
	}

	{
		MeleeShip newSelectedShip;

		newSelectedShip = pMS->currentShip;

		if (PulsedInputState.menu[KEY_MENU_LEFT])
		{
			if (newSelectedShip % NUM_PICK_COLS == 0)
				newSelectedShip += NUM_PICK_COLS;
			--newSelectedShip;
		}
		else if (PulsedInputState.menu[KEY_MENU_RIGHT])
		{
			++newSelectedShip;
			if (newSelectedShip % NUM_PICK_COLS == 0)
				newSelectedShip -= NUM_PICK_COLS;
		}
		
		if (PulsedInputState.menu[KEY_MENU_UP])
		{
			if (newSelectedShip >= NUM_PICK_COLS)
				newSelectedShip -= NUM_PICK_COLS;
			else
				newSelectedShip += NUM_PICK_COLS * (NUM_PICK_ROWS - 1);
		}
		else if (PulsedInputState.menu[KEY_MENU_DOWN])
		{
			if (newSelectedShip < NUM_PICK_COLS * (NUM_PICK_ROWS - 1))
				newSelectedShip += NUM_PICK_COLS;
			else
				newSelectedShip -= NUM_PICK_COLS * (NUM_PICK_ROWS - 1);
		}

		if (newSelectedShip != pMS->currentShip)
			BuildPick_changeSelection (pMS, newSelectedShip);
	}

	Melee_flashSelection (pMS);

	SleepThreadUntil (TimeIn + ONE_SECOND / 30);

	return TRUE;
}

// Returns true if a ship has been selected, or false if the operation has
// been cancelled or if the general abort key was pressed (in which case
// 'GLOBAL (CurrentActivity) & CHECK_ABORT' is true as usual.
// If a ship was selected, pMS->currentShip is set to the selected ship.
bool
BuildPickShip (MELEE_STATE *pMS)
{
	FlushInput ();
	BuildPick_syncMouseState (pMS);

	if (pMS->currentShip == MELEE_NONE)
		pMS->currentShip = 0;

	LockMutex (GraphicsLock);
	DrawPickFrame (pMS);
	UnlockMutex (GraphicsLock);

	pMS->InputFunc = DoPickShip;
	DoInput (pMS, FALSE);
	
	return pMS->buildPickConfirmed;
}

"""Executable requirements model, NOT ESP32 firmware or a certified safety function."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Status:
    homed: bool=False
    y_retracted: bool=False
    local_stop_ok: bool=False
    safety_chain_ok: bool=False
    battery_ok: bool=False
    brake_ready: bool=False
    motion_stopped: bool=True
    outer_door_locked: bool=False
    inner_shutter_closed: bool=True
    inner_shutter_open: bool=False
    tray_has_box: bool=False
    io_has_box: bool=False
    vision_fresh: bool=False
    correct_box_id: bool=False
    camera_calibrated: bool=False


def may_move(axis,status,*,link_age_ms,command_age_ms,session_matches,sequence_new):
    if axis not in ('X','Y','Z'):return False
    if not (session_matches and sequence_new and link_age_ms<250 and command_age_ms<150):return False
    if not (status.local_stop_ok and status.safety_chain_ok and status.battery_ok and status.homed):return False
    if axis in ('X','Z') and not status.y_retracted:return False
    if axis=='Z' and not status.brake_ready:return False
    return True


def may_open_outer(status):
    return status.inner_shutter_closed and not status.inner_shutter_open and status.motion_stopped and status.y_retracted


def may_open_inner(status):
    return status.outer_door_locked and status.motion_stopped and status.y_retracted


def may_close_inner(status):
    return status.motion_stopped and status.y_retracted


def may_transfer_to_io(status):
    return (status.outer_door_locked and status.inner_shutter_open and not status.inner_shutter_closed
            and status.tray_has_box and not status.io_has_box)


def may_transfer_from_io(status):
    return (status.outer_door_locked and status.inner_shutter_open and not status.inner_shutter_closed
            and status.io_has_box and not status.tray_has_box)


def may_apply_visual_correction(status,dx_mm,dz_mm):
    return (status.homed and status.y_retracted and status.local_stop_ok and status.safety_chain_ok
            and status.battery_ok and status.vision_fresh and status.correct_box_id and status.camera_calibrated
            and abs(dx_mm)<=2 and abs(dz_mm)<=2 and status.motion_stopped)


def link_loss_action(axis):
    # Safe stopping distance must be physically measured; this text is not a braking implementation.
    return 'local controlled stop; engage independent fail-safe brake; no auto-resume' if axis=='Z' else 'local controlled stop; no auto-resume'

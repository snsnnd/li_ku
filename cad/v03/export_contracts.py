"""Machine-readable interface/vision handoff from the exported V03 instance table."""
import hashlib
import json
from pathlib import Path
from asrs_v03 import OUT,FINGERPRINT


def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    if manifest['fingerprint']!=FINGERPRINT:raise ValueError('Export current CAD first')
    common={'fingerprint':FINGERPRINT,'units':'mm','hardware_accepted':False}
    interfaces={**common,'column':{'id':'COL-180-P01','pitch':180,
        'carrier_size':[178,170,6],'locator_centers_relative_to_column':[[ -75,75],[75,75]],
        'round_receiver_diameter':6.2,'slot_length_width':[8,6.2],'pin_diameter':6,
        'M6_clamp_centers_relative_to_column':[[-45,20],[45,20],[-45,130],[45,130]],
        'precision_fit_released':False},
        'head':{'id':'HEAD-P01','interface_origin':'X axis centre, Y block centre, Z deck-26',
            'M3_clamp_xy':[[-10,25],[10,25]],'D3_locator_xy':[[-10,35],[10,35]],
            'receiver_round_diameter':3.2,'receiver_slot_length_width':[4.2,3.2]},
        'power_case':{'id':'PWR-P01','shell_size':[155,85,50],'lid_thickness':3,
            'M4_attachment_xy':[[-60,-25],[-60,25],[60,-25],[60,25]],
            'battery_envelope':[85,65,42],'controller_envelope':[40,55,12],
            'connector_selected':False,'hot_swappable':False,
            'lid_finishing':'Current lid 2.8 pilot holes: ream to 3.4 for M3 trial; body 2.5 pilot holes tap M3. Confirm screw length on specimen.'},
        'io':{'id':'IO-P01','box_centre_and_deck':[-150,65,200],
            'human_access_side':'-X','outer_port_y_range':[0,138],'outer_port_z_range':[190,290],
            'inner_shutter_stroke':90,'dual_door_hardware_validated':False}}
    (OUT/'module_interfaces.json').write_text(json.dumps(interfaces,ensure_ascii=False,indent=2))
    tags=[]
    for i in manifest['instances']:
        name=i['name'];ident=None;role=None
        if name=='carried_bin_marker':ident,role=7,'box'
        elif name.startswith('stored_bin_') and name.endswith('_marker'):
            _,_,c,r,_=name.split('_');ident,role=int(c)*5+int(r),'box'
        elif name.startswith('column_') and name.endswith('_reference_tag'):
            ident,role=100+int(name.split('_')[1]),'fixed_column'
        elif name=='io_external_reference_tag':ident,role=200,'external_io_reference'
        if ident is not None:
            xyz=list(i['origin_mm']);xyz[2]+=16
            tags.append({'instance':name,'id':ident,'role':role,'default_centre_mm':xyz,
                'outward_normal':[-1,0,0] if role=='external_io_reference' else [0,-1,0]})
    vision={**common,'family':'tag36h11','card_outer_mm':32,'detected_black_square_mm':25.6,
        'tag_frame_convention':'X right, Y up, Z outward normal; convert detector conventions explicitly',
        'T_bin_from_tag':[[1,0,0,-36],[0,0,-1,-61.2],[0,1,0,38],[0,0,0,1]],
        'initial_layout_only':True,'ids_are_not_storage_coordinates':True,'tags':tags,
        'camera_intrinsics_calibrated':False,'camera_tool_extrinsics_calibrated':False,
        'physical_decode_test_passed':False}
    assert len(tags)==25 and len({t['id'] for t in tags})==25
    (OUT/'vision_layout.json').write_text(json.dumps(vision,ensure_ascii=False,indent=2))
    radio={**common,'contract_version':'0.1-requirements-only','firmware_implemented':False,
        'control_contract_sha256':hashlib.sha256(Path(__file__).with_name('control_contract.py').read_bytes()).hexdigest(),
        'nodes':['X','Z','Y'],'radio_selected':False,'heartbeat_timeout_ms_candidate':250,
        'command_max_age_ms_candidate':150,'message_requirements':['module identity','session identity',
            'strictly increasing sequence','expiry','bounded target in mm','speed and acceleration limits','authenticated origin'],
        'local_requirements':['trajectory generation','hard limits and homing','battery status',
            'watchdog','independent safety-chain input','Z brake/anti-fall feedback','no auto-resume after fault'],
        'ordinary_wifi_is_not_safety_rated':True}
    (OUT/'wireless_contract.json').write_text(json.dumps(radio,ensure_ascii=False,indent=2))
    print('CONTRACTS_EXPORTED',len(tags),'tag placements')


if __name__=='__main__':main()

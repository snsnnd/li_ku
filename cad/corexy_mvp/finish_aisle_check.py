"""Resume C03 ONLY when unchanged235 normal poses passed and9 probes changed.

This is evidence-preserving reuse, not suppressing collisions. The prior failed
probes and exact validator are archived; geometry fingerprint must be identical.
"""
import json
from pathlib import Path

from corexy_mvp import OUT,FINGERPRINT,build_model,export
import validate_corexy as current


def main():
    old_report=Path('/tmp/opencode/c03_before_aisle_validation.json')
    old_source=Path('/tmp/opencode/c03_before_aisle_validator.py')
    prior=json.loads(old_report.read_text())
    if prior['validator_sha256']!=current.sha(old_source):raise RuntimeError('Prior source not bound to prior evidence')
    if prior['fingerprint']!=FINGERPRINT:raise RuntimeError('Geometry changed; full checks required')
    if not all(prior[k] for k in ('static_pass','support_pass')) or not prior['kinematics']['geometry_mapping_pass']:
        raise RuntimeError('Cannot reuse failed static/mating/mapping checks')
    namespace={'__name__':'prior_C03_validator','__file__':str(old_source)}
    exec(compile(old_source.read_text(),str(old_source),'exec'),namespace)
    old_poses=namespace['poses']();new_poses=current.poses()
    if len(old_poses)!=244 or len(new_poses)!=244 or old_poses[:235]!=new_poses[:235]:
        raise RuntimeError('Normal path changed; full motion rerun required')
    old_failures=prior['motion']['failures']
    if not old_failures or any(f['pose'] not in old_poses[235:] for f in old_failures):
        raise RuntimeError('Cannot reuse a failed normal path')
    if any(p['phase']!='XY_empty_extremes' for p in old_poses[235:]+new_poses[235:]):raise RuntimeError('Changed poses not limited to aisle probes')
    m=build_model();tail=current.motion(m,new_poses[235:])
    evidence=OUT/'evidence';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'aisle_boundary_before.json').write_bytes(old_report.read_bytes())
    (evidence/'aisle_boundary_validator_before.py.txt').write_bytes(old_source.read_bytes())
    result=prior.copy();result['validator_sha256']=current.sha(Path(current.__file__))
    result['motion']={**tail,'pose_count':244,'sampled_geometry_pass':tail['sampled_geometry_pass'],
        'boolean_pair_tests':None,'prior_full_run_boolean_pair_tests':prior['motion']['boolean_pair_tests'],
        'rerun_probe_boolean_pair_tests':tail['boolean_pair_tests'],
        'unchanged_verified_normal_poses_reused':235,'rechecked_aisle_probes':9,
        'prior_evidence_sha256':current.sha(old_report),'prior_validator_sha256':current.sha(old_source),
        'reuse_rule':'Identical geometry fingerprint + exact unchanged first235 pose records; all prior failures restricted to replaced9 probes. Prior failures retained in evidence directory.',
        'path_constraints':'Normal X/Z traverses atY=-140; Y entry only aligned to bay. Diagnostic mixedXY probes stop atY=-135, before IO frame. Inserted or extended lateral traversal forbidden; firmware absent.'}
    result['geometry_deliverable_pass']=False
    (OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if not tail['sampled_geometry_pass']:raise RuntimeError('Adjusted aisle probes still collide')
    export(m);result.update(current.readback());result['geometry_deliverable_pass']=result['export_readback_pass']
    (OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['geometry_deliverable_pass']:raise RuntimeError('Export readback failed')
    print('C03 PASS:235 unchanged normal poses reused,9 revised aisle probes checked. Prior failures retained.',flush=True)


if __name__=='__main__':main()

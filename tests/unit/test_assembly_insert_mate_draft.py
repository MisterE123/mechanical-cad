"""Detached composition keeps accepted ownership distinct from insertion seed."""

import copy
import importlib

import pytest
from test_assembly_joint_draft import PACKAGE, fixture, poses

api = importlib.import_module(PACKAGE + '.assembly_insert_mate_draft')


def setup(kind='fixed'):
    accepted = fixture()
    insertion = api.InsertPreviewDraft(
        accepted, 'block', parent='root', parent_frame='origin', child_frame='origin',
        kind=kind, coordinate=0, name='new', joint_name='new attachment',
    )
    seed = insertion.candidate()
    faces = [dict(id=name, kind='face', provenance={'semantic_status':'stable'},
                  signature=dict(surface='plane',area=100,centroid=[5,5,z],normal=[0,0,n]))
             for name,z,n in [('top',10,1),('bottom',0,-1)]]
    response = dict(ok=True, result=dict(
        canonical_assembly=seed, assembly_digest='a'*64, source_hashes={'source':'b'*64},
        instances=copy.deepcopy(seed['instances']), parts=[dict(id='block',topology=faces)],
        source_replays=[{'id':'source'}],
    ),report={'base_pose':{'transforms':poses(seed)}})
    return accepted, insertion, response


def test_original_seed_and_final_candidate_are_distinct_detached_snapshots():
    accepted, insertion, response = setup()
    before = copy.deepcopy((accepted, insertion.candidate(), response))
    draft = api.InsertMateDraft(insertion,response)
    assert draft.original() == accepted and draft.seed() == insertion.candidate()
    assert not draft.has_face_pair
    draft.attach_face_pair('top','bottom')
    candidate = draft.candidate()
    assert draft.has_face_pair and candidate != draft.seed()
    assert candidate['instances'] == draft.seed()['instances']
    assert candidate['joints'][:-1] == accepted['joints']
    assert candidate['part_sources'] == accepted['part_sources']
    assert draft.instance_id == insertion.instance_id and draft.joint_id == insertion.joint_id
    frame_ids = [f['id'] for f in candidate['parts'][0]['mate_frames']]
    draft.attach_face_pair('top','bottom')
    assert draft.candidate() == candidate
    assert [f['id'] for f in draft.candidate()['parts'][0]['mate_frames']] == frame_ids
    assert (accepted,insertion.candidate(),response) == before
    response['result']['parts'].clear()
    draft.original()['instances'].clear()
    draft.seed()['parts'].clear()
    assert draft.candidate() == candidate


def test_failed_second_face_does_not_partially_adopt_new_parent():
    _, insertion, response = setup()
    draft = api.InsertMateDraft(insertion,response)
    draft.attach_face_pair('top','bottom')
    before = draft.candidate()
    with pytest.raises(api.BridgeError):
        draft.attach_face_pair('bottom','missing')
    assert draft.candidate() == before and draft.has_face_pair


@pytest.mark.parametrize('fault',['canonical','instances','parts','pose','failed','kind','type'])
def test_rejects_mismatched_incomplete_or_unsupported_seed(fault):
    _, insertion, response = setup('slider' if fault=='kind' else 'fixed')
    if fault=='canonical':
        response['result']['canonical_assembly']['name']='other'
    elif fault=='instances':
        response['result']['instances'][-1]['id']='other'
    elif fault=='parts':
        response['result']['parts'].append(copy.deepcopy(response['result']['parts'][0]))
    elif fault=='pose':
        response['report']['base_pose']['transforms'].pop('root')
    elif fault=='failed':
        response['ok']=False
    elif fault=='type':
        insertion=object()
    with pytest.raises(api.BridgeError):
        api.InsertMateDraft(insertion,response)

import numpy as np
import pytest

from cranio.landmark_proposals import held_out_errors, propose

A = np.array([[0.,0,0], [10,0,0], [0,12,0], [0,0,15], [2,3,5]])
LIMITS = dict(gap_mm=1., anchor_radius_mm=20., anchor_limit_mm=2.)


def test_registered_nonlinear_fixture_and_held_out_error():
    # Independent synthetic polynomial displacement, then a similarity. Oracle
    # projects onto the true z=0 face; it does not return the hidden x/y labels.
    def warp(p):
        p = np.array(p, float)
        p[:,0] += .012*p[:,1]*p[:,2]
        return 1.2*p[:,[1,2,0]] + [30,-10,20]
    sample = np.array([[1.,1,0],[1,2,0],[2,1,0]])
    def nearest(points):
        out = points.copy()
        out[:,1] = -10
        return out
    sites = {'held-A':[2.,2,0], 'held-B':[3.,1,0], 'far':[100.,100,100]}
    args = (A,warp(A),sample,sites,nearest)
    r = propose(*args, **LIMITS)
    assert r == propose(*args, **LIMITS)
    r['anchors'] = {'used-anchor': []}
    score = held_out_errors(r,dict(zip(sites,warp(list(sites.values())))))
    assert score['compared_count'] == 2 and score['unassessed'] == ['far']
    assert score['median_mm'] < .2  # software fixture only
    assert all(r['sites'][k]['status']=='needs_review' for k in ('held-A','held-B'))
    assert r['sites']['far']['world_mm'] is None
    assert r['icp_iterations'] > 0 and r['surface_inliers'] == len(sample)
    with pytest.raises(ValueError, match='registration anchors'):
        held_out_errors(r, {'used-anchor':A[0]})
    print('Synthetic held-out median (mm):', score['median_mm'])


def test_missing_support_and_config_limits():
    sites = {'hole':[2.,2.,4.]}
    def plane(p):
        out = p.copy()
        out[:,2] = 0.
        return out
    r = propose(A,A,A,sites,plane,**LIMITS)
    assert r['sites']['hole']['reason'] == 'no observed surface within limit'
    assert held_out_errors(r,sites)['median_mm'] is None
    with pytest.raises(ValueError, match='positive'):
        propose(A,A,A,sites,plane,**dict(LIMITS,gap_mm=0))
    with pytest.raises(ValueError, match='No reference surface'):
        propose(A,A,A,sites,lambda p:p+999,**LIMITS)


@pytest.mark.parametrize('change,match', [
    (lambda x:x*[-1,1,1], 'reflected'),
    (lambda x:x*[1,1,0], 'degenerate'),
    (lambda x:np.vstack((x[:-1],x[0])), 'distinct'),
    (lambda x:x+np.eye(len(x),3)*30, 'reflected|residual'),
    (lambda x:x*float('nan'), 'NaN'),
])
def test_invalid_anchors(change, match):
    with pytest.raises(ValueError, match=match):
        propose(A,change(A),A,{'query':A[0]},lambda p:p,**LIMITS)

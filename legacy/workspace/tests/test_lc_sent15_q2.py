"""Toy and architecture guards for the frozen Q2 matrix."""
from __future__ import annotations
import unittest
import torch
from memoryflow.lc_sent15_q2 import DIM, EXPECTED_PARAMETERS, GROUP_SIZE, grouped_loss, make_head, parameter_count, validate_heads

class Q2Tests(unittest.TestCase):
 def test_nine_cell_matrix(self): self.assertEqual(len(EXPECTED_PARAMETERS)*3,9)
 def test_parameter_counts(self): validate_heads()
 def test_h2_symmetry(self):
  torch.manual_seed(0); m=make_head('H2_R_SYM_128').eval(); t,s=torch.randn(2,DIM),torch.randn(2,DIM); self.assertTrue(torch.allclose(m(t,s),m(s,t),atol=1e-7,rtol=0))
 def test_h3_is_directional_unshared(self):
  m=make_head('H3_D_FULL_64'); self.assertEqual(m.net[0].in_features,4*DIM+1); self.assertEqual(parameter_count(m),EXPECTED_PARAMETERS['H3_D_FULL_64'])
 def test_listwise_toy(self):
  z=torch.arange(GROUP_SIZE,dtype=torch.float); y=torch.tensor([1]+[0]*(GROUP_SIZE-1),dtype=torch.bool); g=torch.zeros(GROUP_SIZE,dtype=torch.long); self.assertTrue(torch.allclose(grouped_loss('L1_LISTWISE_CE',z,y,g),-torch.log_softmax(z,0)[0]))
 def test_pairwise_toy(self):
  z=torch.tensor([2.]+[1.]*(GROUP_SIZE-1));y=torch.tensor([1]+[0]*(GROUP_SIZE-1),dtype=torch.bool);g=torch.zeros(GROUP_SIZE,dtype=torch.long); self.assertTrue(torch.allclose(grouped_loss('L2_PAIRWISE_SOFTPLUS',z,y,g),torch.nn.functional.softplus(torch.tensor(-1.))))
 def test_balanced_bce_toy(self):
  z=torch.zeros(GROUP_SIZE);y=torch.tensor([1]+[0]*(GROUP_SIZE-1),dtype=torch.bool);g=torch.zeros(GROUP_SIZE,dtype=torch.long);self.assertTrue(torch.allclose(grouped_loss('L3_BALANCED_POINTWISE_BCE',z,y,g),torch.tensor(0.69314718),atol=1e-6))
 def test_requires_exactly_one_positive(self):
  with self.assertRaises(ValueError): grouped_loss('L1_LISTWISE_CE',torch.zeros(GROUP_SIZE),torch.zeros(GROUP_SIZE,dtype=torch.bool),torch.zeros(GROUP_SIZE,dtype=torch.long))

if __name__=='__main__': unittest.main()

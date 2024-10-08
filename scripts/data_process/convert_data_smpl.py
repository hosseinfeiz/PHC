from ast import Try
import torch
import joblib
import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage
from scipy.spatial.transform import Rotation as sRot
import glob
import os
import sys
import pdb
import os.path as osp

sys.path.append(os.getcwd())

# from smpl_sim.khrylib.utils import get_body_qposaddr
from smpl_sim.smpllib.smpl_mujoco_new import SMPL_BONE_ORDER_NAMES as joint_names
from smpl_sim.smpllib.smpl_local_robot import SMPL_Robot as LocalRobot
import scipy.ndimage.filters as filters
from typing import List, Optional
from tqdm import tqdm
from poselib.poselib.skeleton.skeleton3d import SkeletonTree, SkeletonMotion, SkeletonState

robot_cfg = {
    "mesh": False,
    "model": "smpl",
    "upright_start": True,
    "body_params": {},
    "joint_params": {},
    "geom_params": {},
    "actuator_params": {},
}
print(robot_cfg)

smpl_local_robot = LocalRobot(
    robot_cfg,
    data_dir="data/smpl",
)

amass_data = np.load("Dataset/0_poses.npz")

double = False

mujoco_joint_names = ['Pelvis', 'L_Hip', 'L_Knee', 'L_Ankle', 'L_Toe', 'R_Hip', 'R_Knee', 'R_Ankle', 'R_Toe', 'Torso', 'Spine', 'Chest', 'Neck', 'Head', 'L_Thorax', 'L_Shoulder', 'L_Elbow', 'L_Wrist', 'L_Hand', 'R_Thorax', 'R_Shoulder', 'R_Elbow', 'R_Wrist', 'R_Hand']

 

amass_remove_data = []

full_motion_dict = {}
for key_name in tqdm(amass_data.keys()):
    smpl_data_entry = amass_data[key_name]
    B = amass_data['poses'][:,:72].shape[0]

    start, end = 0, 0

    pose_aa = amass_data['poses'][:,:72].copy()[start:][::2]
    root_trans = amass_data['trans'].copy()[start:][::2]
    B = pose_aa.shape[0]

    beta = amass_data['beta'].copy() if "beta" in amass_data else amass_data['betas'].copy()
    if len(beta.shape) == 2:
        beta = beta[0]

    gender = amass_data.get("gender", "neutral")
    fps = amass_data.get("frame_rate", 30.0)

    if isinstance(gender, np.ndarray):
        gender = gender.item()

    if isinstance(gender, bytes):
        gender = gender.decode("utf-8")
    if gender == "neutral":
        gender_number = [0]
    elif gender == "male":
        gender_number = [1]
    elif gender == "female":
        gender_number = [2]
    else:
        import ipdb
        ipdb.set_trace()
        raise Exception("Gender Not Supported!!")

    smpl_2_mujoco = [joint_names.index(q) for q in mujoco_joint_names if q in joint_names]
    batch_size = pose_aa.shape[0]
    pose_aa = np.concatenate([pose_aa[:, :66], np.zeros((batch_size, 6))], axis=1)
    pose_aa_mj = pose_aa.reshape(-1, 24, 3)[..., smpl_2_mujoco, :].copy()

    num = 1
    if double:
        num = 2
    for idx in range(num):
        pose_quat = sRot.from_rotvec(pose_aa_mj.reshape(-1, 3)).as_quat().reshape(batch_size, 24, 4)

        gender_number, beta[:], gender = [0], 0, "neutral"
        print("using neutral model")

        smpl_local_robot.load_from_skeleton(betas=torch.from_numpy(beta[None,]), gender=gender_number, objs_info=None)
        smpl_local_robot.write_xml("phc/data/assets/mjcf/smpl_humanoid_1.xml")
        skeleton_tree = SkeletonTree.from_mjcf("phc/data/assets/mjcf/smpl_humanoid_1.xml")

        root_trans_offset = torch.from_numpy(root_trans) + skeleton_tree.local_translation[0]

        new_sk_state = SkeletonState.from_rotation_and_root_translation(
            skeleton_tree,  # This is the wrong skeleton tree (location wise) here, but it's fine since we only use the parent relationship here. 
            torch.from_numpy(pose_quat),
            root_trans_offset,
            is_local=True)

        if robot_cfg['upright_start']:
            pose_quat_global = (sRot.from_quat(new_sk_state.global_rotation.reshape(-1, 4).numpy()) * sRot.from_quat([0.5, 0.5, 0.5, 0.5]).inv()).as_quat().reshape(B, -1, 4)  # should fix pose_quat as well here...

            new_sk_state = SkeletonState.from_rotation_and_root_translation(skeleton_tree, torch.from_numpy(pose_quat_global), root_trans_offset, is_local=False)
            pose_quat = new_sk_state.local_rotation.numpy()

            ############################################################
            # key_name_dump = key_name + f"_{idx}"
            key_name_dump = key_name
            if idx == 1:
                left_to_right_index = [0, 5, 6, 7, 8, 1, 2, 3, 4, 9, 10, 11, 12, 13, 19, 20, 21, 22, 23, 14, 15, 16, 17, 18]
                pose_quat_global = pose_quat_global[:, left_to_right_index]
                pose_quat_global[..., 0] *= -1
                pose_quat_global[..., 2] *= -1

                root_trans_offset[..., 1] *= -1
            ############################################################

        new_motion_out = {}
        new_motion_out['pose_quat_global'] = pose_quat_global
        new_motion_out['pose_quat'] = pose_quat
        new_motion_out['trans_orig'] = root_trans
        new_motion_out['root_trans_offset'] = root_trans_offset
        new_motion_out['beta'] = beta
        new_motion_out['gender'] = gender
        new_motion_out['pose_aa'] = pose_aa
        new_motion_out['fps'] = fps
        full_motion_dict[key_name_dump] = new_motion_out

joblib.dump(full_motion_dict, "p1.pkl")

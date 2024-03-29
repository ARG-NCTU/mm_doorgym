#! /usr/bin/env python3

import os
import rospy
import time 
import yaml
import numpy as np
from std_srvs.srv import Trigger
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from gazebo_msgs.srv import *
from gazebo_msgs.msg import *

class GoalNav(object):
    def __init__(self):
        super().__init__()

        self.my_dir = os.path.abspath(os.path.dirname(__file__))
        self.yaml = rospy.get_param("~yaml")

        # read yaml
        with open(os.path.join(self.my_dir,"../../../../Config/" + self.yaml), 'r') as f:
            data = yaml.load(f)

        self.goal_totoal = data["pairs"]

        self.total_traj = []

        # metric
        self.count = 0
        self.total = len(self.goal_totoal)
        self.success = 0
        self.coi = 0
        self.cnt = 0
        self.collision_states = False

        self.goal_pub = rospy.Publisher("/tare/goal", PoseStamped, queue_size=1)
        self.state_pub = rospy.Publisher('/state', String, queue_size=10)
        self.get_robot_pos = rospy.ServiceProxy("/gazebo/get_model_state", GetModelState)
        self.sub_collision = rospy.Subscriber("/robot/bumper_states", ContactsState, self.cb_collision, queue_size=1)
        self.set_init_pose_srv = rospy.ServiceProxy("/gazebo/set_model_state", SetModelState)
        self.set_door_srv = rospy.ServiceProxy("/gazebo/set_model_configuration", SetModelConfiguration)
        self.arm_home_srv = rospy.ServiceProxy("/robot/ur5/go_home", Trigger)
        self.loop()

    def loop(self):

        while(1):

            if(self.count == self.total):
                # finish all goal

                # calculate metric
                s_r = (self.success/self.total) * 100
                f_r = 100 - s_r
                a_c = self.coi / self.total

                # output result 
                d = {'success_rate':s_r, "fail_rate":f_r, "average_coillision":a_c}

                tra = {'environment' : "room_door", "policy": "TARE", "trajectories" : self.total_traj}

                with open(os.path.join(self.my_dir,"../../../../Results/TARE_trajectory.yaml"), "w") as f:

                    yaml.dump(tra, f)

                with open(os.path.join(self.my_dir,"../../../../Results/TARE_result.yaml"), "w") as f:

                    yaml.dump(d, f)
                
                rospy.loginfo('End')
                break
            else:
                req = ModelState()
                req.model_name = 'robot'
                req.pose.position.x = self.goal_totoal[self.count]['start'][0]
                req.pose.position.y = self.goal_totoal[self.count]['start'][1]
                req.pose.position.z = 0.1323
                req.pose.orientation.x = 0.0
                req.pose.orientation.y = 0.0
                req.pose.orientation.z = -0.707
                req.pose.orientation.w = 0.707

                # set robot
                self.set_init_pose_srv(req)

                # set door 
                self.set_door_srv("hinge_door_0", "", ["hinge"], [0])

                # set arm
                self.arm_home_srv()

                # set goal
                self.goal = self.goal_totoal[self.count]['goal'][0:2]

                self.count += 1
                self.inference()

    def cb_collision(self, msg):
        if self.collision_states == True:
            if msg.states == [] and self.cnt > 4000:
                self.collision_states = False
            else:
                self.cnt += 1
        elif msg.states != [] and self.cnt == 0:
            self.collision_states = True
            self.coi += 1
        else:
            self.collision_states = False
            self.cnt = 0

    def inference(self):

        # publish goal to tare
        pose = PoseStamped()

        pose.header.frame_id = "map"
        pose.pose.position.x = self.goal[0]
        pose.pose.position.y = self.goal[1]

        self.goal_pub.publish(pose)

        # publish state to enable tare start
        self.state_pub.publish("nav")

        begin = time.time()

        tra = []

        # check robot navigate to goal
        while(1):

            robot_pose = self.get_robot_pos("robot", "")
            r_pose = {"position" : [robot_pose.pose.position.x, robot_pose.pose.position.y, robot_pose.pose.position.z],
                      "orientation" : [robot_pose.pose.orientation.x, robot_pose.pose.orientation.y, robot_pose.pose.orientation.z, robot_pose.pose.orientation.w]}
            tra.append(r_pose)

            robot_pose = self.get_robot_pos("robot","")

            x, y = robot_pose.pose.position.x, robot_pose.pose.position.y
            dis = np.linalg.norm(self.goal - np.array([x, y])) 

            if(dis < 0.8):
                
                self.success += 1
                self.state_pub.publish("stop")
                self.total_traj.append(tra[0:-1:50])
                break

            if((time.time() - begin) >= 60):
                self.state_pub.publish("stop")
                self.total_traj.append(tra[0:-1:50])
                break

            cur_x, cur_y = x,y

if __name__ == "__main__":
    rospy.init_node("loop_node")
    goalNav = GoalNav()
    rospy.spin()
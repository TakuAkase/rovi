#include <ros/ros.h>
#include <std_srvs/Trigger.h>
#include <std_msgs/String.h>
#include <geometry_msgs/Point32.h>
#include <sensor_msgs/PointCloud.h>
#include <sensor_msgs/PointCloud2.h>
#include <sensor_msgs/point_cloud_conversion.h>
#include <opencv2/opencv.hpp>
#include <cv_bridge/cv_bridge.h>
#include <sensor_msgs/Image.h>
#include "rovi/Floats.h"
#include "rovi/GenPC.h"
#include "ps_main.h"
#include <stdio.h>

//#define PLYDUMP

bool isready = false;

ros::NodeHandle *nh;
ros::Publisher *pub1,*pub2,*pub3,*pub4;

std::vector<double> vecQ;
std::vector<double> cam_K;
int cam_width,cam_height;
std::string file_dump("/tmp");
PS_PARAMS param = {
  .search_div = PH_SEARCH_DIV,
  .bw_diff = BW_DIFF,
  .brightness = BRIGHTNESS,
  .darkness = DARKNESS,
  .step_diff = STEP_DIFF,
  .max_step = MAX_STEP,
  .max_ph_diff = MAX_PH_DIFF,
  .max_tex_diff = MAX_TEX_DIFF,
  .max_parallax = MAX_PARALLAX,
  .min_parallax = MIN_PARALLAX,
  .right_dup_cnt = RIGHT_DUP_N,
  .ls_points = LS_POINTS,
  .evec_error = EVEC_ERROR,
};

int reload(){
  nh->getParam("pshift_genpc/calc/search_div", param.search_div);
  nh->getParam("pshift_genpc/calc/bw_diff", param.bw_diff);
  nh->getParam("pshift_genpc/calc/brightness", param.brightness);
  nh->getParam("pshift_genpc/calc/darkness", param.darkness);
  nh->getParam("pshift_genpc/calc/step_diff", param.step_diff);
  nh->getParam("pshift_genpc/calc/max_step", param.max_step);
  nh->getParam("pshift_genpc/calc/max_ph_diff", param.max_ph_diff);
  nh->getParam("pshift_genpc/calc/max_tex_diff", param.max_tex_diff);
  nh->getParam("pshift_genpc/calc/max_parallax", param.max_parallax);
  nh->getParam("pshift_genpc/calc/min_parallax", param.min_parallax);
  nh->getParam("pshift_genpc/calc/right_dup_cnt", param.right_dup_cnt);
  nh->getParam("pshift_genpc/calc/ls_points", param.ls_points);

  nh->getParam("genpc/Q", vecQ); 
  if (vecQ.size() != 16){
    ROS_ERROR("Param Q NG");
    return -1;
  }
  nh->getParam("left/remap/K", cam_K);
  if (cam_K.size() != 9){
    ROS_ERROR("Param K NG");
    return -1;
  }
  nh->getParam("left/remap/width", cam_width);
  nh->getParam("left/remap/height", cam_height);
  if(nh->hasParam("genpc/dump")) nh->getParam("genpc/dump",file_dump);
  else file_dump="";
  if (vecQ.size() != 16){
    ROS_ERROR("Param Q NG");
    return -1;
  }

  ROS_INFO("genpc:reload ok");
  return 0;
}

sensor_msgs::ImagePtr to_depth(std::vector<geometry_msgs::Point32> ps){
  float centre_x=cam_K[2];
  float centre_y=cam_K[5];
  float focal_x=cam_K[0];
  float focal_y=cam_K[4];
  cv::Mat cv_image = cv::Mat(cam_height, cam_width, CV_32FC1,cv::Scalar(std::numeric_limits<float>::max()));
  for (int i=0; i<ps.size();i++){
    float z = ps[i].z;
    float u = ps[i].x * focal_x / z;
    float v = ps[i].y * focal_y / z;
    int pixel_pos_x = (int)(u + centre_x);
    int pixel_pos_y = (int)(v + centre_y);
    if (pixel_pos_x > (cam_width-1)) pixel_pos_x = cam_width -1;
    else if (pixel_pos_x < 0) pixel_pos_x = 0;
    if (pixel_pos_y > (cam_height-1)) pixel_pos_y = cam_height-1;
    else if (pixel_pos_y < 0) pixel_pos_y = 0;
    cv_image.at<float>(pixel_pos_y,pixel_pos_x) = z;
  }
  return cv_bridge::CvImage(std_msgs::Header(), "32FC1", cv_image).toImageMsg();
}

struct XYZW{ float x,y,z,w;};
bool operator<(const XYZW& left, const XYZW& right){ return left.w < right.w;}

union PACK{ float d[3]; char a[12];};
std::string base64encode(const std::vector<geometry_msgs::Point32> data) {
  static const char sEncodingTable[] = {
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H',
    'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P',
    'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X',
    'Y', 'Z', 'a', 'b', 'c', 'd', 'e', 'f',
    'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n',
    'o', 'p', 'q', 'r', 's', 't', 'u', 'v',
    'w', 'x', 'y', 'z', '0', '1', '2', '3',
    '4', '5', '6', '7', '8', '9', '+', '/'
  };
  size_t in_len=data.size();
  size_t out_len=sizeof(float)*3*in_len*4/3;
  std::string ret(out_len,'\x0');
  PACK u;
  for(int i=0,j=0;i<in_len;i++){
    u.d[0]=data[i].x;
    u.d[1]=data[i].y;
    u.d[2]=data[i].z;
    for(int k=0;k<12;k+=3){
      ret[j++]=sEncodingTable[(u.a[k]>>2)&0x3F];
      ret[j++]=sEncodingTable[((u.a[k]&0x3)<<4) | ((int)(u.a[k+1]&0xF0)>>4)];
      ret[j++]=sEncodingTable[((u.a[k+1]&0xF)<<2) | ((int)(u.a[k+2]&0xC0)>>6)];
      ret[j++]=sEncodingTable[u.a[k+2]&0x3F];
    }
  }
  return ret;
}

bool genpc(rovi::GenPC::Request &req, rovi::GenPC::Response &res){
  ROS_INFO("genpc called: %d %d", req.imgL.size(), req.imgR.size());

  if (!isready) {
    int width = req.imgL[0].width;
    int height = req.imgL[0].height;
    ROS_INFO("genpc img w, h: %d %d", width, height);
    ps_init(width, height);
    ROS_INFO("ps_init done");
    isready=true;
  }
  reload();
  ps_setparams(param);

//read Phase Shift data images. (13 left images and 13 right images)
  try
  {
    for (int j = 0; j < 13; j++)
    {
      cv::Mat img = cv_bridge::toCvCopy(req.imgL[j], sensor_msgs::image_encodings::MONO8)->image;
      ps_setpict(0, j, img);
      if(file_dump.size()>0) cv::imwrite(cv::format((file_dump+"/capt%02d_0.pgm").c_str(), j), img);
      img = cv_bridge::toCvCopy(req.imgR[j], sensor_msgs::image_encodings::MONO8)->image;
      ps_setpict(1, j, img);
      if(file_dump.size()>0) cv::imwrite(cv::format((file_dump+"/capt%02d_1.pgm").c_str(), j), img);
    }
    if(file_dump.size()>0){
      FILE *f=fopen((file_dump+"/captseq.log").c_str(),"w");
      for(int j=0;j<13;j++){
        fprintf(f,"(%d) %d %d\n",j,req.imgL[j].header.seq,req.imgR[j].header.seq);
      }
      fclose(f);
    }
  }
  catch (cv_bridge::Exception& e)
  {
    ROS_ERROR("genpc:cv_bridge:exception: %s", e.what());
    return false;
  }
//Do calc
  ROS_INFO("before ps_exec");
  Eigen::MatrixXd &diff = ps_exec();
  Eigen::Matrix4d Q;
  ROS_INFO("before memcpy");
  memcpy(Q.data(), vecQ.data(), sizeof(double) * 4 * 4);
  ROS_INFO("before genPC");
  int N = genPC(diff, ps.texture, ps.mask[0], ps.pt, Q);
//output point clouds
  sensor_msgs::PointCloud pts;
  pts.header.stamp = ros::Time::now();
  pts.header.frame_id = "/camera";
  if(N==0){
    pub1->publish(pts);
    std_msgs::String b64;
    pub2->publish(b64);
    rovi::Floats buf;
    pub3->publish(buf);
    res.pc_cnt = N;
    ROS_INFO("genpc point count 0");
    return true;
  }
  pts.points.resize(N);
  pts.channels.resize(3);
  pts.channels[0].name = "r";
  pts.channels[0].values.resize(N);
  pts.channels[1].name = "g";
  pts.channels[1].values.resize(N);
  pts.channels[2].name = "b";
  pts.channels[2].values.resize(N);
//building point cloud, getting center of points, and getting norm from the center
  double X0=0,Y0=0,Z0=0;  
  for (int n = 0; n < N; n++){
    X0+=pts.points[n].x = _pcd[n].coord[0];
    Y0+=pts.points[n].y = _pcd[n].coord[1];
    Z0+=pts.points[n].z = _pcd[n].coord[2];
    pts.channels[0].values[n] = _pcd[n].col[0] / 255.0;
    pts.channels[1].values[n] = _pcd[n].col[1] / 255.0;
    pts.channels[2].values[n] = _pcd[n].col[2] / 255.0;
  }
  X0/=N; Y0/=N; Z0/=N;
//  X0=Y0=Z0=0;
//getting norm from the center and sort by it
  std::vector<XYZW> norm;
  norm.resize(N);
  for (int n = 0; n < N; n++){
    float dx=(norm[n].x=pts.points[n].x)-X0;
    float dy=(norm[n].y=pts.points[n].y)-Y0;
    float dz=(norm[n].z=pts.points[n].z)-Z0;
//  norm[n].w=sqrt(dx*dx+dy*dy+dz*dz);
    norm[n].w=sqrt(dx*dx+dy*dy);
  }
  std::sort(norm.begin(),norm.end());
//Quantize points count for Numpy array
  rovi::Floats buf;
  double gamma=1.2;
  double kn=floor((log10(N)-1)/log10(gamma));
  int Qn=N<10? N:floor(10*pow(gamma,kn));
  buf.data.resize(3*Qn);
  for (int n = 0; n < Qn; n++){
    int n3=3*n;
    buf.data[n3++]=norm[n].x;
    buf.data[n3++]=norm[n].y;
    buf.data[n3]=norm[n].z;
  }
  if(file_dump.size()>0){
    ROS_INFO("before outPLY");
    outPLY((file_dump+"/test.ply").c_str());
    outPLY((file_dump+"/testRG.ply").c_str(), RANGE_GRID);
    ROS_INFO("after  outPLY");
  }
  pub1->publish(pts);
  std_msgs::String b64;
  b64.data=base64encode(pts.points);
  pub2->publish(b64);
  pub3->publish(buf);
  pub4->publish(to_depth(pts.points));

  res.pc_cnt = N;
  ROS_INFO("genPC point counts %d / %d",N,Qn);
  return true;
}

int main(int argc, char **argv){
  ros::init(argc, argv, "genpc_node");
  ros::NodeHandle n;
  nh = &n;
  if(reload()<0) return 1;

  ros::ServiceServer svc1 = n.advertiseService("genpc", genpc);
  ros::Publisher p1 = n.advertise<sensor_msgs::PointCloud>("ps_pc", 1);
  pub1 = &p1;
  ros::Publisher p2 = n.advertise<std_msgs::String>("ps_base64", 1);
  pub2 = &p2;
  ros::Publisher p3 = n.advertise<rovi::Floats>("ps_floats", 1);
  pub3 = &p3;
  ros::Publisher p4 = n.advertise<sensor_msgs::Image>("image_depth", 1);
  pub4 = &p4;
  ros::spin();
  return 0;
}

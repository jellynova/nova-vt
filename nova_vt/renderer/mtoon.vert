#version 330 core

layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;
layout(location = 2) in vec2 in_uv;
layout(location = 3) in ivec4 in_joints;
layout(location = 4) in vec4 in_weights;

uniform mat4 u_joint_matrices[128];
uniform mat4 u_mvp;

out vec3 v_normal;
out vec2 v_uv;

void main() {
    mat4 skin_mat =
        in_weights.x * u_joint_matrices[in_joints.x] +
        in_weights.y * u_joint_matrices[in_joints.y] +
        in_weights.z * u_joint_matrices[in_joints.z] +
        in_weights.w * u_joint_matrices[in_joints.w];

    vec4 world_pos = skin_mat * vec4(in_position, 1.0);
    gl_Position = u_mvp * world_pos;

    mat3 normal_mat = transpose(inverse(mat3(skin_mat)));
    v_normal = normalize(normal_mat * in_normal);
    v_uv = in_uv;
}

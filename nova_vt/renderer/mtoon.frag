#version 330 core

in vec3 v_normal;
in vec2 v_uv;

uniform vec4 u_lit_color;
uniform vec4 u_shade_color;
uniform float u_shade_shift;
uniform float u_shade_toony;
uniform vec3 u_light_dir;
uniform float u_alpha_cutoff;

uniform sampler2D u_lit_texture;
uniform int u_has_texture;

out vec4 out_color;

void main() {
    vec4 tex_color = u_has_texture == 1
        ? texture(u_lit_texture, v_uv)
        : vec4(1.0);

    float ndotl = dot(v_normal, normalize(-u_light_dir));
    float toon = ndotl * 0.5 + 0.5;
    toon = clamp((toon + u_shade_shift) * (1.0 + u_shade_toony), 0.0, 1.0);

    vec4 color = mix(u_shade_color, u_lit_color, toon) * tex_color;

    if (u_alpha_cutoff > 0.0 && color.a < u_alpha_cutoff) discard;
    out_color = color;
}

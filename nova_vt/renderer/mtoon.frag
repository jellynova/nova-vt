#version 330 core

in vec3 v_normal;
in vec2 v_uv;

// MToon lighting uniforms
uniform vec4 u_lit_color;       // base diffuse colour (RGBA)
uniform vec4 u_shade_color;     // shadow colour (RGBA)
uniform float u_shade_shift;    // -1..1, toon shadow boundary
uniform float u_shade_toony;    // 0..1, shadow blending sharpness
uniform vec3 u_light_dir;       // world-space light direction (normalised)
uniform float u_alpha_cutoff;   // 0 = opaque, >0 = cutout

// Texture
uniform sampler2D u_lit_texture;
uniform int u_has_texture;

out vec4 out_color;

void main() {
    vec4 tex_color = u_has_texture == 1
        ? texture(u_lit_texture, v_uv)
        : vec4(1.0);

    // Toon shading: compute NdotL, shift, clamp into 0..1 toon factor
    float ndotl = dot(v_normal, normalize(-u_light_dir));
    float toon = ndotl * 0.5 + 0.5;  // remap -1..1 → 0..1
    toon = clamp((toon + u_shade_shift) * (1.0 + u_shade_toony), 0.0, 1.0);

    vec4 color = mix(u_shade_color, u_lit_color, toon) * tex_color;

    if (u_alpha_cutoff > 0.0 && color.a < u_alpha_cutoff) discard;
    out_color = color;
}

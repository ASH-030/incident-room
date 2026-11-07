import type { NextConfig } from 'next';
const config: NextConfig = {async headers(){return [{source:'/:path*',headers:[{key:'X-Content-Type-Options',value:'nosniff'},{key:'Referrer-Policy',value:'strict-origin-when-cross-origin'},{key:'Cross-Origin-Opener-Policy',value:'same-origin-allow-popups'}]}]},async rewrites(){return [{source:'/api/:path*',destination:`${process.env.ROOM_API_URL || 'http://127.0.0.1:8400'}/api/:path*`}];}};
export default config;

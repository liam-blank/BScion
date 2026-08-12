#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <limits>
#include <queue>
#include <string>
#include <utility>
#include <vector>
#ifdef _OPENMP
#include <omp.h>
#endif

struct Pair { uint32_t node; float weight; };
struct OutRec { uint32_t block; uint32_t source; float distance; };

template <typename T> std::vector<T> read_vec(const std::string& path) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  if (!f) throw std::runtime_error("cannot open " + path);
  auto size=f.tellg(); f.seekg(0);
  std::vector<T> v(static_cast<size_t>(size)/sizeof(T));
  f.read(reinterpret_cast<char*>(v.data()), size);
  return v;
}

int main(int argc,char** argv){
  if(argc<8){
    std::cerr << "usage: bounded_reach offsets.bin neighbors.bin weights.bin block_nodes.bin sources.bin maxdist output.bin\n";
    return 2;
  }
  auto offsets=read_vec<uint64_t>(argv[1]);
  auto nbr=read_vec<uint32_t>(argv[2]);
  auto w=read_vec<float>(argv[3]);
  auto block_nodes=read_vec<uint32_t>(argv[4]);
  auto sources=read_vec<uint32_t>(argv[5]);
  const float maxdist=std::stof(argv[6]);
  const std::string outbase=argv[7];
  const uint32_t n=static_cast<uint32_t>(offsets.size()-1);

  std::vector<std::vector<uint32_t>> blocks_at(n);
  for(uint32_t b=0;b<block_nodes.size();++b){
    if(block_nodes[b]<n) blocks_at[block_nodes[b]].push_back(b);
  }

  int threads=1;
  #ifdef _OPENMP
  threads=omp_get_max_threads();
  #endif
  std::vector<std::string> parts(threads);
  for(int t=0;t<threads;++t) parts[t]=outbase+".part"+std::to_string(t);

  #pragma omp parallel
  {
    int tid=0;
    #ifdef _OPENMP
    tid=omp_get_thread_num();
    #endif
    std::ofstream out(parts[tid],std::ios::binary);
    std::vector<float> dist(n,std::numeric_limits<float>::infinity());
    std::vector<uint32_t> touched; touched.reserve(20000);
    using Q=std::pair<float,uint32_t>;
    std::priority_queue<Q,std::vector<Q>,std::greater<Q>> pq;

    #pragma omp for schedule(dynamic,8)
    for(uint32_t sidx=0;sidx<sources.size();++sidx){
      uint32_t source=sources[sidx];
      if(source>=n) continue;
      while(!pq.empty()) pq.pop();
      touched.clear();
      dist[source]=0.0f; touched.push_back(source); pq.push({0.0f,source});
      while(!pq.empty()){
        auto [du,u]=pq.top(); pq.pop();
        if(du!=dist[u]) continue;
        if(du>maxdist) break;
        if(!blocks_at[u].empty()){
          for(uint32_t b:blocks_at[u]){
            OutRec r{b,sidx,du}; out.write(reinterpret_cast<const char*>(&r),sizeof(r));
          }
        }
        for(uint64_t k=offsets[u];k<offsets[u+1];++k){
          uint32_t v=nbr[k]; float nd=du+w[k];
          if(nd<=maxdist && nd<dist[v]){
            if(!std::isfinite(dist[v])) touched.push_back(v);
            dist[v]=nd; pq.push({nd,v});
          }
        }
      }
      for(uint32_t v:touched) dist[v]=std::numeric_limits<float>::infinity();
    }
  }

  std::ofstream final(outbase,std::ios::binary);
  for(const auto& p:parts){
    std::ifstream in(p,std::ios::binary); final << in.rdbuf(); in.close(); std::remove(p.c_str());
  }
  std::cerr << "sources=" << sources.size() << " threads=" << threads << " output=" << outbase << "\n";
  return 0;
}

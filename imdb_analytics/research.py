"""Vote-floor sensitivity on an authorized local IMDb snapshot; aggregate exports only."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import statistics
import sys

FLOORS=(100,1000,10000,100000)
GENRES=('Action','Adventure','Animation','Biography','Comedy','Crime','Documentary',
        'Drama','Family','Fantasy','History','Horror','Music','Musical','Mystery',
        'Romance','Sci-Fi','Sport','Thriller','War','Western')
ROOT=Path(__file__).resolve().parent


def records(con, sql, params):
    cur=con.execute(sql,params)
    return [dict(zip([c[0] for c in cur.description],r)) for r in cur.fetchall()]


def analyze(con,start_year=2000,end_year=2024,top_n=50):
    if start_year>end_year or top_n<1:raise ValueError('Invalid year window or shortlist size')
    params={'start_year':start_year,'end_year':end_year}
    base='''SELECT t.title_id,t.premiered,t.genres,r.rating,r.votes
     FROM titles t JOIN ratings r USING(title_id)
     WHERE t.type='movie' AND t.is_adult=0 AND t.premiered BETWEEN :start_year AND :end_year'''
    # Load independent simple records to reconcile SQL windowed aggregations.
    source=records(con,base,params)
    summary=records(con,(ROOT/'queries/vote_floor_research.sql').read_text(),params)
    by_floor={r['vote_floor']:r for r in summary}
    baseline=[r for r in source if r['votes']>=FLOORS[0]]
    if not baseline:raise ValueError('No baseline titles in declared window')
    genre_rows=[];year_rows=[];shortlists={}
    years=sorted({r['premiered'] for r in baseline})
    base_year_counts={y:sum(r['premiered']==y for r in baseline) for y in years}
    base_year_mean={y:statistics.mean(r['rating'] for r in baseline if r['premiered']==y) for y in years}
    for floor in FLOORS:
        sample=[r for r in source if r['votes']>=floor]
        if floor not in by_floor:
            if sample:raise AssertionError('SQL omitted a populated floor')
            continue
        row=by_floor[floor]
        assert row['n_titles']==len(sample)
        assert abs(row['mean_title_rating']-statistics.mean(r['rating'] for r in sample))<1e-10
        assert abs(row['median_title_rating']-statistics.median(r['rating'] for r in sample))<1e-10
        row['baseline_retention']=len(sample)/len(baseline)
        shortlists[floor]=[r['title_id'] for r in sorted(sample,key=lambda r:(-r['rating'],-r['votes'],r['title_id']))[:top_n]]
        for genre in GENRES:
            query='''WITH sample AS ('''+base+''' AND r.votes>=:floor)
             SELECT COUNT(*) AS denominator,
             SUM(CASE WHEN instr(','||COALESCE(genres,'')||',',','||:genre||',')>0 THEN 1 ELSE 0 END) AS tagged
             FROM sample'''
            result=records(con,query,{**params,'floor':floor,'genre':genre})[0]
            count=sum(genre in (r['genres'] or '').split(',') for r in sample)
            assert result['denominator']==len(sample) and result['tagged']==count
            genre_rows.append({'vote_floor':floor,'genre':genre,'tagged_titles':count,
                               'denominator':len(sample),'share':count/len(sample)})
        standardized_delta=0.;covered_weight=0.
        for y in years:
            group=[r for r in sample if r['premiered']==y]
            n=len(group);mean=statistics.mean(r['rating'] for r in group) if n else None
            weight=base_year_counts[y]/len(baseline)
            year_rows.append({'vote_floor':floor,'release_year':y,'n_titles':n,
                              'baseline_n':base_year_counts[y],'retention':n/base_year_counts[y],
                              'mean_title_rating':mean,'baseline_year_weight':weight})
            if n:
                standardized_delta+=weight*(mean-base_year_mean[y]);covered_weight+=weight
        # Do not silently reweight when a year has no observations at this floor.
        row['baseline_year_standardized_rating_delta']=standardized_delta if abs(covered_weight-1)<1e-12 else None
        row['standardization_covered_weight']=covered_weight
    baseline_short=set(shortlists[FLOORS[0]])
    for floor,row in by_floor.items():
        current=set(shortlists[floor]);intersection=len(current & baseline_short)
        row['shortlist_n']=len(current);row['baseline_shortlist_n']=len(baseline_short)
        row['shortlist_overlap_count']=intersection
        row['baseline_shortlist_retention']=intersection/len(baseline_short)
        row['shortlist_jaccard']=intersection/len(current|baseline_short)
        row['shortlist_new_count']=len(current-baseline_short)
    return {'config':{'start_year':start_year,'end_year':end_year,'vote_floors':list(FLOORS),'shortlist_size':top_n},
            'joined_movies_in_window':len(source),'threshold_summary':summary,
            'genre_mix':genre_rows,'year_sensitivity':year_rows}


def write_csv(path,rows):
    if not rows:raise ValueError('No result rows to export')
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def write_reports(result,output):
    output.mkdir(parents=True,exist_ok=True)
    manifest = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'config': result['config'],
        'import_metadata': result.get('import_metadata', {}),
        'note': 'Generation time is not the source snapshot or retrieval date. Input hashes identify the local source files.',
    }
    (output/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for key in ['threshold_summary','genre_mix','year_sensitivity']:
        write_csv(output/(key+'.csv'),result[key])
    (output/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n')
    rows=result['threshold_summary'];low=rows[0];mid=next(r for r in rows if r['vote_floor']==10000)
    genres=result['genre_mix'];g0={r['genre']:r['share'] for r in genres if r['vote_floor']==100}
    g1={r['genre']:r['share'] for r in genres if r['vote_floor']==10000}
    shifts=sorted(((g,g1[g]-g0[g]) for g in g0),key=lambda x:abs(x[1]),reverse=True)
    lines=['# IMDb vote-floor sensitivity','',
      'Question: how does requiring more audience votes change a movie-review pool and its apparent quality?',
      '',f"Scope: non-adult IMDb movies released {result['config']['start_year']}–{result['config']['end_year']}; joined to observed ratings. Input fingerprints and run metadata are in run_manifest.json.",
      '', '| Minimum votes | Titles | Retained vs 100 votes | Mean title rating | Median rating | Top-50 retained |',
      '| ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in rows:lines.append(f"| {r['vote_floor']:,} | {r['n_titles']:,} | {r['baseline_retention']:.1%} | {r['mean_title_rating']:.3f} | {r['median_title_rating']:.2f} | {r['shortlist_overlap_count']} / {r['baseline_shortlist_n']} |")
    lines+=['','## Findings','',
      f"Increasing the vote floor from 100 to 10,000 retains {mid['baseline_retention']:.1%} of the baseline pool ({mid['n_titles']:,} of {low['n_titles']:,} movies). The mean of title-level ratings changes from {low['mean_title_rating']:.3f} to {mid['mean_title_rating']:.3f}. This is selection, not an improvement in the films or a causal effect of voting.",
      f"The top-{result['config']['shortlist_size']} shortlist retains {mid['shortlist_overlap_count']} of {mid['baseline_shortlist_n']} baseline titles and introduces {mid['shortlist_new_count']} replacements. Ranking is rating descending, votes descending, title ID ascending.",
      '', 'Largest genre-share shifts at 10,000 versus 100 votes:']
    for g,d in shifts[:5]:lines.append(f'- {g}: {g0[g]:.1%} to {g1[g]:.1%} ({d*100:+.1f} percentage points).')
    delta=mid['baseline_year_standardized_rating_delta']
    lines+=['',f"Holding release-year weights at the baseline distribution, the mean-rating difference is {delta:+.3f} points." if delta is not None else 'Year-standardized comparison is unavailable because a release year has no eligible titles.',
      '', '## Recommendation', '',
      'Display vote eligibility alongside a shortlist and compare genre mix before adopting a high threshold. A high vote floor is a support rule; it also changes coverage. For discovery, keep a separate lower-vote review lane instead of silently excluding it. These findings do not identify an optimal threshold or establish commercial demand.',
      '', '## Definitions and limits', '',
      'Each title receives equal weight in the reported mean. IMDb averageRating is itself a provider-weighted user-rating measure. Votes are cumulative participation as of the snapshot, not unique viewers, sales, or revenue. Genre shares overlap because movies may have up to three tags; unknown genres remain in the denominator. Runtime is not required for inclusion. Release-year standardization compares within-year mean differences using fixed baseline-year weights; it does not remove language, geography, survival or audience-selection bias. The predeclared 100/1,000/10,000/100,000 vote floors are sensitivity scenarios, not optimized cutoffs.',
      '', 'Source datasets and the SQLite database remain local and are not redistributed. The original missing classroom database has not been reconstructed; this is a new, documented official-data extension. Aggregate numerical outputs are reconciled independently against the imported records.',
      '', 'Source: https://data.imdb.com/non-commercial-datasets/']
    (output/'findings.md').write_text('\n'.join(lines)+'\n')


def plot(result,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'svg.fonttype':'none'})
    rows=result['threshold_summary'];x=list(range(len(rows)))
    fig,axes=plt.subplots(1,2,figsize=(11,4.8),gridspec_kw={'width_ratios':[1,1.2]})
    fig.subplots_adjust(left=.08,right=.97,top=.78,bottom=.24,wspace=.4)
    fig.suptitle('Vote requirements change the movie pool',x=.08,y=.97,ha='left',fontsize=17,fontweight='bold')
    config = result['config']
    fig.text(.08,.86,f"IMDb movies released {config['start_year']}–{config['end_year']} | Local input fingerprints: run_manifest.json",fontsize=10,color='#4b5563')
    ax=axes[0];bars=ax.bar(x,[r['baseline_retention']*100 for r in rows],color='#253f57',width=.6)
    ax.set_xticks(x,[f"{r['vote_floor']:,}" for r in rows]);ax.set_xlabel('Minimum cumulative votes');ax.set_ylabel('Baseline movie pool retained (%)');ax.set_ylim(0,115)
    for bar,r in zip(bars,rows):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+2,f"{r['n_titles']:,}\n({r['baseline_retention']:.1%})",ha='center',va='bottom',fontsize=9)
    gs=result['genre_mix'];a={r['genre']:r['share'] for r in gs if r['vote_floor']==100};b={r['genre']:r['share'] for r in gs if r['vote_floor']==10000}
    shifts=sorted(((g,100*(b[g]-a[g])) for g in a),key=lambda x:abs(x[1]),reverse=True)[:6]
    shifts.sort(key=lambda x:x[1]);names,values=zip(*shifts)
    ax=axes[1];ax.barh(names,values,color=['#a95a42' if v<0 else '#253f57' for v in values]);ax.axvline(0,color='#777777',linewidth=.7)
    ax.set_xlabel('Genre share change (percentage points)');ax.set_title('10,000 versus 100 votes',fontsize=11,loc='left')
    fig.text(.08,.07,'Genre memberships overlap. Vote counts measure participation, not demand.\nSource: official IMDb non-commercial datasets. Aggregated by title; no causal or revenue claim.',fontsize=9,color='#4b5563')
    fig.savefig(output/'vote_floor_review.svg');fig.savefig(output/'vote_floor_review.png',dpi=180);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('outputs/research'));args=p.parse_args()
    path=args.database.resolve()
    if not path.is_file():p.error('Database does not exist')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as con:
        result=analyze(con)
        try:result['import_metadata']=dict(con.execute('SELECT key,value FROM import_metadata'))
        except sqlite3.OperationalError:result['import_metadata']={}
    write_reports(result,args.output);plot(result,args.output)
    print(json.dumps(result['threshold_summary'],indent=2))


if __name__=='__main__':main()


import {Composition} from 'remotion';
import {CoreEquityTrailer} from './CoreEquityTrailer';

export const Root = () => {
  return (
    <Composition
      id="CoreEquityNextWeek"
      component={CoreEquityTrailer}
      durationInFrames={1260}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{
        launchLine: 'LA SEMAINE PROCHAINE',
      }}
    />
  );
};

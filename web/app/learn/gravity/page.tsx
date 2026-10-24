import { Formula } from "../../../components/learn/Formula";
import { LessonHead } from "../../../components/learn/LessonHead";
import { Band } from "../../../components/site/Band";

// A placeholder so the index link resolves; the lesson itself replaces it.
export default function GravityLesson() {
  return (
    <main className="page">
      <LessonHead n={1} title="Does the ball obey gravity?" level="Foundations" />
      <Band>
        <p className="lesson-draft">Draft: this lesson is being written.</p>
        <Formula label="The gravity read from the fitted flight">
          <mrow>
            <msub>
              <mi>g</mi>
              <mtext>data</mtext>
            </msub>
            <mo>=</mo>
            <mo>−</mo>
            <mn>2</mn>
            <mi>a</mi>
          </mrow>
        </Formula>
      </Band>
    </main>
  );
}
